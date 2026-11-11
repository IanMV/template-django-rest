from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db.models.query import QuerySet
from django.utils import timezone

from core.models import EmailChange, EmailVerification, PasswordReset, User
from tests.base import ApiCase


class MaintenanceTests(ApiCase):
    def cleanup(self):
        call_command("cleanup_auth", stdout=StringIO())

    def abandoned(self, email="old@example.com", **fields):
        user = User.objects.create(email=email, is_active=False, **fields)
        User.objects.filter(pk=user.pk).update(
            created_at=timezone.now() - timedelta(hours=49)
        )
        return user

    def test_cleanup_preserves_accounts_and_live_registrations(self):
        missing = self.abandoned()
        expired = self.abandoned("expired@example.com")
        exhausted = self.abandoned("exhausted@example.com")
        EmailVerification.objects.create(
            user=expired, code="hash", expires_at=timezone.now()
        )
        EmailVerification.objects.create(
            user=exhausted,
            code="hash",
            used=True,
            used_at=timezone.now(),
            attempts=5,
            expires_at=timezone.now(),
        )
        preserved = [
            self.abandoned("disabled@example.com", password="!"),
            self.abandoned("staff@example.com", is_staff=True),
            self.abandoned("super@example.com", is_superuser=True),
            self.abandoned("live@example.com"),
            User.objects.create(email="recent@example.com", is_active=False),
            self.create_user(email="active@example.com"),
        ]
        EmailVerification.objects.create(user=preserved[3], code="hash")
        self.cleanup()
        self.assertFalse(
            User.objects.filter(pk__in=[missing.pk, expired.pk, exhausted.pk]).exists()
        )
        self.assertEqual(
            User.objects.filter(pk__in=[user.pk for user in preserved]).count(),
            len(preserved),
        )

    def test_cleanup_expired_codes_and_sessions(self):
        user = self.create_user()
        for model in (EmailVerification, PasswordReset, EmailChange):
            model.objects.create(user=user, code="hash", expires_at=timezone.now())
        self.login(user)
        Session.objects.update(expire_date=timezone.now())
        self.cleanup()
        for model in (EmailVerification, PasswordReset, EmailChange):
            self.assertFalse(model.objects.exists())
        self.assertFalse(Session.objects.exists())

    def test_expired_registration_marker_is_kept_until_user_is_old_enough(self):
        user = User.objects.create(email="recent@example.com", is_active=False)
        marker = EmailVerification.objects.create(
            user=user, code="hash", expires_at=timezone.now()
        )
        self.cleanup()
        self.assertTrue(EmailVerification.objects.filter(pk=marker.pk).exists())

    def test_cleanup_rechecks_selected_accounts_before_deleting(self):
        user = self.abandoned()
        lock = User.objects.select_for_update

        def confirmed_before_lock(*args, **kwargs):
            User.objects.filter(pk=user.pk).update(is_active=True, password="defined")
            return lock(*args, **kwargs)

        with patch.object(
            User.objects, "select_for_update", side_effect=confirmed_before_lock
        ):
            self.cleanup()
        self.assertTrue(User.objects.filter(pk=user.pk, is_active=True).exists())

    def test_cleanup_preserves_every_nonprovisional_state(self):
        preserved = [
            self.abandoned("named@example.com", name="Managed registration"),
            self.abandoned("login@example.com", last_login=timezone.now()),
            self.abandoned("version@example.com", session_version=1),
            self.abandoned("group@example.com"),
            self.abandoned("permission@example.com"),
            self.abandoned("history@example.com"),
            self.abandoned("reset@example.com"),
            self.abandoned("change@example.com"),
        ]
        preserved[3].groups.add(Group.objects.create(name="Preserved"))
        preserved[4].user_permissions.add(
            Permission.objects.get(content_type__app_label="core", codename="view_user")
        )
        LogEntry.objects.create(
            user=preserved[5],
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(preserved[5].pk),
            object_repr="Managed registration",
            action_flag=ADDITION,
        )
        PasswordReset.objects.create(user=preserved[6], code="hash")
        EmailChange.objects.create(
            user=preserved[7], code="hash", new_email="destination@example.com"
        )
        removable = self.abandoned("empty@example.com")
        for user in preserved:
            self.assertFalse(user.is_provisional_registration)
        self.assertTrue(removable.is_provisional_registration)
        self.cleanup()
        self.assertEqual(
            User.objects.filter(pk__in=[user.pk for user in preserved]).count(),
            len(preserved),
        )
        self.assertFalse(User.objects.filter(pk=removable.pk).exists())

    def test_admin_enrichment_of_public_registration_prevents_cleanup(self):
        self.assertEqual(
            self.client.post(
                "/api/registration/request/", {"email": "pending@example.com"}
            ).status_code,
            201,
        )
        pending = User.objects.get(email="pending@example.com")
        self.login(
            self.create_user(
                email="admin@example.com", is_staff=True, is_superuser=True
            )
        )
        path = f"/admin/core/user/{pending.pk}/change/"
        token = (
            self.client.get(path).context["adminform"].form["security_state"].value()
        )
        group = Group.objects.create(name="Managed")
        response = self.client.post(
            path,
            {
                "email": pending.email,
                "name": "Enriched registration",
                "groups": [str(group.pk)],
                "security_state": token,
            },
        )
        self.assertEqual(response.status_code, 302)
        pending.refresh_from_db()
        self.assertFalse(pending.is_active)
        self.assertEqual(pending.password, "")
        with patch(
            "django.utils.timezone.now",
            return_value=timezone.now() + timedelta(hours=49),
        ):
            self.cleanup()
        pending.refresh_from_db()
        self.assertEqual(pending.name, "Enriched registration")
        self.assertTrue(pending.groups.filter(pk=group.pk).exists())

    def test_cleanup_rechecks_enrichment_after_selecting_candidates(self):
        for relation in (False, True):
            with self.subTest(relation=relation):
                user = self.abandoned(f"candidate-{relation}@example.com")
                lock = User.objects.select_for_update

                def enrich_before_lock(*args, **kwargs):
                    if relation:
                        user.groups.add(Group.objects.create(name="Added before lock"))
                    else:
                        User.objects.filter(pk=user.pk).update(name="Added before lock")
                    return lock(*args, **kwargs)

                with patch.object(
                    User.objects, "select_for_update", side_effect=enrich_before_lock
                ):
                    self.cleanup()
                self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_delete_failure_rolls_back_batch(self):
        user = self.abandoned()
        delete = QuerySet.delete

        def broken_delete(queryset):
            result = delete(queryset)
            if queryset.model is User:
                raise RuntimeError("delete failed")
            return result

        with patch.object(QuerySet, "delete", broken_delete):
            with self.assertRaisesMessage(RuntimeError, "delete failed"):
                self.cleanup()
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
