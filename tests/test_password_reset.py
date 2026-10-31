from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from core.models.password_reset import PasswordReset
from core.models.user import UserSession
from tests.base import ApiCase, ApiTransactionCase


class PasswordResetTests(ApiCase):
    base_url = "/api/password-reset/"

    def request_code(self, email):
        response = self.post_with_commit(self.base_url + "request/", {"email": email})
        self.assertEqual(response.status_code, 200, response.data)
        return self.email_code()

    def test_request_sends_hashed_code(self):
        user = self.create_user()
        code = self.request_code(user.email)
        self.assertEqual(mail.outbox[-1].to, [user.email])
        self.assertNotEqual(PasswordReset.objects.get(user=user).code, code)

    def test_unknown_and_inactive_email_return_same_response_without_mail(self):
        inactive = self.create_user(is_active=False)
        missing = self.client.post(
            self.base_url + "request/",
            {"email": "missing@example.com"},
            format="json",
            REMOTE_ADDR="127.0.0.1",
        )
        inactive_response = self.client.post(
            self.base_url + "request/",
            {"email": inactive.email},
            format="json",
            REMOTE_ADDR="127.0.0.2",
        )
        self.assertEqual(
            (missing.status_code, missing.data),
            (inactive_response.status_code, inactive_response.data),
        )
        self.assertEqual(missing.status_code, 200)
        self.assertFalse(mail.outbox)

    def test_verify_does_not_consume_and_confirm_revokes_every_session(self):
        user = self.create_user()
        self.login(user)
        other = self.new_client()
        self.login(user, client=other, ip="127.0.0.2")
        code = self.request_code(user.email)
        payload = {"email": user.email, "code": code}
        self.assertEqual(
            self.client.post(
                self.base_url + "verify/", payload, format="json"
            ).status_code,
            200,
        )
        record = PasswordReset.objects.get(user=user)
        self.assertFalse(record.used)
        response = self.client.post(
            self.base_url + "confirm/",
            {**payload, "new_password": "DifferentPass!7395"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        user.refresh_from_db()
        self.assertTrue(user.check_password("DifferentPass!7395"))
        record.refresh_from_db()
        self.assertTrue(record.used)
        self.assertFalse(UserSession.objects.filter(user=user, is_active=True).exists())
        self.assertEqual(BlacklistedToken.objects.filter(token__user=user).count(), 2)
        self.assertEqual(other.get("/api/users/me/").status_code, 401)
        self.assertEqual(
            self.client.post(
                self.base_url + "confirm/",
                {**payload, "new_password": "DifferentPass!7395"},
                format="json",
            ).status_code,
            400,
        )

    def test_five_wrong_attempts_exhaust_code(self):
        user = self.create_user()
        code = self.request_code(user.email)
        wrong = "000000" if code != "000000" else "999999"
        for attempt in range(5):
            self.assertEqual(
                self.client.post(
                    self.base_url + "verify/",
                    {"email": user.email, "code": wrong},
                    format="json",
                ).status_code,
                400,
                attempt,
            )
        record = PasswordReset.objects.get(user=user)
        self.assertEqual(record.attempts, 5)
        self.assertEqual(
            self.client.post(
                self.base_url + "verify/",
                {"email": user.email, "code": code},
                format="json",
            ).status_code,
            400,
        )

    def test_code_expires_after_fifteen_minutes(self):
        user = self.create_user()
        code = self.request_code(user.email)
        expiry = PasswordReset.objects.get(user=user).expires_at
        with patch("django.utils.timezone.now", return_value=expiry):
            response = self.client.post(
                self.base_url + "verify/",
                {"email": user.email, "code": code},
                format="json",
            )
        self.assertEqual(response.status_code, 400)

    def test_new_request_replaces_used_code_and_resets_expiry(self):
        user = self.create_user()
        previous = self.request_code(user.email)
        record = PasswordReset.objects.get(user=user)
        old_pk, old_expiry = record.pk, record.expires_at
        record.used = True
        record.save(update_fields=["used"])
        cache.clear()
        with patch(
            "django.utils.timezone.now",
            return_value=timezone.now() + timedelta(minutes=1),
        ):
            current = self.request_code(user.email)
        record = PasswordReset.objects.get(user=user)
        self.assertNotEqual(record.pk, old_pk)
        self.assertFalse(record.used)
        self.assertEqual(record.attempts, 0)
        self.assertGreater(record.expires_at, old_expiry)
        self.assertEqual(
            self.client.post(
                self.base_url + "verify/",
                {"email": user.email, "code": previous},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.base_url + "verify/",
                {"email": user.email, "code": current},
                format="json",
            ).status_code,
            200,
        )

    def test_password_similarity_rejects_name(self):
        user = self.create_user()
        code = self.request_code(user.email)
        response = self.client.post(
            self.base_url + "confirm/",
            {"email": user.email, "code": code, "new_password": user.name},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password(self.password))

    def test_send_failure_does_not_disclose_account_or_leave_code(self):
        user = self.create_user()
        with patch(
            "core.password_reset.services.send_email_token",
            side_effect=RuntimeError("mail down"),
        ):
            with self.assertLogs("core.password_reset.services", level="ERROR"):
                response = self.post_with_commit(
                    self.base_url + "request/", {"email": user.email}
                )
        unknown = self.client.post(
            self.base_url + "request/",
            {"email": "missing@example.com"},
            format="json",
            REMOTE_ADDR="127.0.0.2",
        )
        self.assertEqual((response.status_code, response.data), (unknown.status_code, unknown.data))
        self.assertFalse(PasswordReset.objects.filter(user=user).exists())


class PasswordResetAttemptPersistenceTests(ApiTransactionCase):
    def test_failed_confirmation_persists_attempt_after_400(self):
        user = self.create_user()
        self.assertEqual(
            self.client.post(
                "/api/password-reset/request/", {"email": user.email}, format="json"
            ).status_code,
            200,
        )
        code = self.email_code()
        wrong = "000000" if code != "000000" else "999999"
        response = self.client.post(
            "/api/password-reset/confirm/",
            {"email": user.email, "code": wrong, "new_password": "DifferentPass!7395"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PasswordReset.objects.get(user=user).attempts, 1)
