from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.admin import ModelAdmin
from django.contrib.admin.sites import AdminSite
from django.db import OperationalError, connection, connections, transaction
from django.test import RequestFactory

from core.admin import UserAdmin
from core.models import EmailChange, EmailVerification, PasswordReset, User
from core.password_reset.services import PasswordResetService
from core.users.services import UserService
from tests.base import ApiCase, ApiTransactionCase


class AdminEmailSecurityTests(ApiCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_user()
        self.admin = self.create_user(
            email="admin@example.com", is_staff=True, is_superuser=True
        )
        self.login(self.admin)
        for model in (PasswordReset, EmailChange, EmailVerification):
            record = model(user=self.owner)
            if model is EmailChange:
                record.new_email = "pending@example.com"
            record.set_code("123456")
            record.save()

    def change_email(self):
        return self.client.post(
            f"/admin/core/user/{self.owner.pk}/change/",
            {"email": "new@example.com", "name": self.owner.name, "is_active": "on"},
        )

    def test_admin_email_change_invalidates_all_pending_codes(self):
        self.assertEqual(self.change_email().status_code, 302)
        for model in (PasswordReset, EmailChange, EmailVerification):
            self.assertFalse(model.objects.filter(user=self.owner).exists())
        public = self.new_client()
        self.bootstrap(public)
        response = public.post(
            "/api/password-reset/confirm/",
            {
                "email": "new@example.com",
                "code": "123456",
                "new_password": "ReplacementPass!7395",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password(self.password))

    def test_admin_email_change_and_code_invalidation_roll_back_together(self):
        with patch(
            "core.admin.SessionService.revoke_all_sessions",
            side_effect=RuntimeError("revocation failed"),
        ):
            with self.assertRaisesMessage(RuntimeError, "revocation failed"):
                self.change_email()
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, "person@example.com")
        for model in (PasswordReset, EmailChange, EmailVerification):
            self.assertTrue(model.objects.filter(user=self.owner).exists())


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class AdminConcurrencyTests(ApiTransactionCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_user()
        self.owner_client, _ = self.login(self.owner, client=self.new_client())
        admin = self.create_user(
            email="admin@example.com", is_staff=True, is_superuser=True
        )
        self.login(admin)

    def test_admin_post_holds_user_lock_until_transaction_finishes(self):
        request = RequestFactory().post("/admin/")
        admin = UserAdmin(User, AdminSite())

        def try_lock():
            try:
                with transaction.atomic():
                    User.objects.select_for_update(nowait=True).get(pk=self.owner.pk)
                return True
            except OperationalError as exc:
                if getattr(exc.__cause__, "sqlstate", None) != "55P03":
                    raise
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                self.assertEqual(
                    admin.get_object(request, str(self.owner.pk)).pk, self.owner.pk
                )
                self.assertFalse(executor.submit(try_lock).result(timeout=20))
            self.assertTrue(executor.submit(try_lock).result(timeout=20))

    def mutate_after_initial_read(self, mutation):
        get_object = ModelAdmin.get_object

        def get_then_mutate(admin, request, object_id, from_field=None):
            obj = get_object(admin, request, object_id, from_field)
            if obj is not None and obj.pk == self.owner.pk:

                def worker():
                    try:
                        mutation()
                    finally:
                        connections.close_all()

                with ThreadPoolExecutor(max_workers=1) as executor:
                    executor.submit(worker).result(timeout=20)
            return obj

        return patch.object(ModelAdmin, "get_object", get_then_mutate)

    def test_admin_name_edit_does_not_restore_password_or_session_version(self):
        reset = PasswordReset(user=self.owner)
        reset.set_code("123456")
        reset.save()

        def reset_password():
            PasswordResetService.confirm_reset(
                self.owner.email, "123456", "ReplacementPass!7395"
            )

        with self.mutate_after_initial_read(reset_password):
            response = self.client.post(
                f"/admin/core/user/{self.owner.pk}/change/",
                {"email": self.owner.email, "name": "Edited", "is_active": "on"},
            )
        self.assertEqual(response.status_code, 302)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.name, "Edited")
        self.assertTrue(self.owner.check_password("ReplacementPass!7395"))
        self.assertEqual(self.owner.session_version, 1)
        self.assertEqual(self.owner_client.get("/api/users/me/").status_code, 401)

    def test_admin_password_change_does_not_restore_deactivated_account(self):
        def deactivate():
            UserService.deactivate_user(
                User.objects.get(pk=self.owner.pk), self.password
            )

        with self.mutate_after_initial_read(deactivate):
            response = self.client.post(
                f"/admin/core/user/{self.owner.pk}/password/",
                {
                    "password1": "ReplacementPass!7395",
                    "password2": "ReplacementPass!7395",
                    "usable_password": "true",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)
        self.assertEqual(self.owner.session_version, 1)
        self.assertTrue(self.owner.check_password("ReplacementPass!7395"))
        self.assertEqual(self.owner_client.get("/api/users/me/").status_code, 401)
