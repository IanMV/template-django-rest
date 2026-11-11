from datetime import timedelta
from io import StringIO
from unittest.mock import patch

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
