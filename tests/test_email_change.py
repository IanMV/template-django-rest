from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError
from django.utils import timezone

from core.auth.services import SessionService
from core.email_change.services import EmailChangeService
from core.models import PasswordReset
from core.models.email_change import EmailChange
from tests.base import ApiCase, ApiTransactionCase


class EmailChangeTests(ApiCase):
    base_url = "/api/email-change/"
    new_email = "new@example.com"

    def request_code(self):
        response = self.post_with_commit(
            self.base_url + "request/",
            {"new_email": self.new_email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200, response.data)
        return self.email_code()

    def test_request_sends_hashed_code_to_new_address(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        self.assertEqual(mail.outbox[-1].to, [self.new_email])
        self.assertNotEqual(EmailChange.objects.get(user=user).code, code)

    def test_request_requires_correct_current_password_without_issuing_code(self):
        user = self.create_user()
        self.login(user)
        path = self.base_url + "request/"
        missing = self.client.post(path, {"new_email": self.new_email}, format="json")
        wrong = self.client.post(
            path,
            {"new_email": self.new_email, "password": "wrong"},
            format="json",
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn("password", missing.data)
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(str(wrong.data["password"]), "Invalid current password.")
        self.assertFalse(EmailChange.objects.filter(user=user).exists())
        self.assertFalse(mail.outbox)

    def test_failed_reauthentication_is_limited_per_user(self):
        user = self.create_user()
        self.login(user)
        for _ in range(5):
            response = self.client.post(
                self.base_url + "request/",
                {"new_email": self.new_email, "password": "wrong"},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        blocked = self.client.post(
            self.base_url + "request/",
            {"new_email": self.new_email, "password": self.password},
            format="json",
            REMOTE_ADDR="127.0.0.2",
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertFalse(EmailChange.objects.filter(user=user).exists())

    def test_reauthentication_cache_failure_fails_closed(self):
        user = self.create_user()
        self.login(user)
        with patch("core.auth.rate_limit.cache.get", side_effect=RuntimeError("down")):
            with self.assertNoLogs("core.auth.rate_limit", level="ERROR"):
                response = self.client.post(
                    self.base_url + "request/",
                    {"new_email": self.new_email, "password": self.password},
                    format="json",
                )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(EmailChange.objects.filter(user=user).exists())

    def test_reauthentication_cache_write_failure_fails_closed(self):
        user = self.create_user()
        self.login(user)
        with patch("core.auth.rate_limit.cache.add", side_effect=RuntimeError("down")):
            with self.assertNoLogs("core.auth.rate_limit", level="ERROR"):
                response = self.client.post(
                    self.base_url + "request/",
                    {"new_email": self.new_email, "password": "wrong"},
                    format="json",
                )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(EmailChange.objects.filter(user=user).exists())

    def test_successful_reauthentication_resets_failed_attempts(self):
        user = self.create_user()
        self.login(user)
        for _ in range(4):
            self.assertEqual(
                self.client.post(
                    self.base_url + "request/",
                    {"new_email": self.new_email, "password": "wrong"},
                    format="json",
                ).status_code,
                400,
            )
        self.request_code()
        for _ in range(5):
            self.assertEqual(
                self.client.post(
                    self.base_url + "request/",
                    {"new_email": self.new_email, "password": "wrong"},
                    format="json",
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.post(
                self.base_url + "request/",
                {"new_email": self.new_email, "password": "wrong"},
                format="json",
            ).status_code,
            429,
        )

    def test_confirm_password_attempts_share_request_throttle(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        for _ in range(5):
            response = self.client.post(
                self.base_url + "confirm/",
                {"code": code, "password": "wrong"},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        blocked = self.client.post(
            self.base_url + "request/",
            {"new_email": "other@example.com", "password": self.password},
            format="json",
            REMOTE_ADDR="127.0.0.2",
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(EmailChange.objects.get(user=user).new_email, self.new_email)

    def test_confirm_changes_email_revokes_every_session_and_clears_cookies(self):
        user = self.create_user()
        self.login(user)
        other = self.new_client()
        self.login(user, client=other, ip="127.0.0.2")
        code = self.request_code()
        record = EmailChange.objects.get(user=user)
        self.assertFalse(record.used)
        response = self.client.post(
            self.base_url + "confirm/",
            {"code": code, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        user.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(user.email, self.new_email)
        self.assertTrue(record.used)
        self.assertEqual(user.session_version, 1)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]["max-age"], 0)
        self.assertEqual(other.get("/api/users/me/").status_code, 401)
        self.login(user)
        self.assertEqual(
            self.client.post(
                self.base_url + "confirm/",
                {"code": code, "password": self.password},
                format="json",
            ).status_code,
            400,
        )

    def test_wrong_current_password_does_not_consume_code(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        response = self.client.post(
            self.base_url + "confirm/",
            {"code": code, "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(EmailChange.objects.get(user=user).used)
        user.refresh_from_db()
        self.assertNotEqual(user.email, self.new_email)

    def test_email_change_invalidates_old_mailbox_reset_code(self):
        user = self.create_user()
        self.login(user)
        self.post_with_commit("/api/password-reset/request/", {"email": user.email})
        old_code = self.email_code()
        change_code = self.request_code()
        changed = self.client.post(
            self.base_url + "confirm/",
            {"code": change_code, "password": self.password},
            format="json",
        )
        self.assertEqual(changed.status_code, 200)
        self.assertFalse(PasswordReset.objects.filter(user=user).exists())
        old_reset = self.client.post(
            "/api/password-reset/confirm/",
            {
                "email": self.new_email,
                "code": old_code,
                "new_password": "ChangedPass!7395",
            },
            format="json",
        )
        self.assertEqual(old_reset.status_code, 400)
        issued = self.post_with_commit(
            "/api/password-reset/request/",
            {"email": self.new_email},
            REMOTE_ADDR="127.0.0.2",
        )
        self.assertEqual(issued.status_code, 200)
        reset = self.client.post(
            "/api/password-reset/confirm/",
            {
                "email": self.new_email,
                "code": self.email_code(),
                "new_password": "ChangedPass!7395",
            },
            format="json",
        )
        self.assertEqual(reset.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("ChangedPass!7395"))

    def test_email_change_rollback_preserves_reset_code(self):
        user = self.create_user()
        self.login(user)
        self.post_with_commit("/api/password-reset/request/", {"email": user.email})
        reset_id = PasswordReset.objects.get(user=user).pk
        change_code = self.request_code()
        with patch.object(
            SessionService,
            "revoke_all_sessions",
            side_effect=RuntimeError("Revocation failed"),
        ):
            with self.assertRaisesMessage(RuntimeError, "Revocation failed"):
                EmailChangeService.confirm_change(user, change_code, self.password)
        self.assertTrue(PasswordReset.objects.filter(pk=reset_id).exists())
        user.refresh_from_db()
        self.assertEqual(user.email, "person@example.com")
        self.assertFalse(EmailChange.objects.get(user=user).used)

    def test_new_email_uniqueness_is_rechecked_on_confirm(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        self.create_user(email=self.new_email)
        response = self.client.post(
            self.base_url + "confirm/",
            {"code": code, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_email", response.data)
        user.refresh_from_db()
        self.assertEqual(user.email, "person@example.com")

    def test_confirm_handles_integrity_error_on_concurrent_email_claim(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        with patch.object(user, "save", side_effect=IntegrityError("duplicate key")):
            with patch(
                "core.models.user.User.save",
                side_effect=IntegrityError("duplicate key"),
            ):
                response = self.client.post(
                    self.base_url + "confirm/",
                    {"code": code, "password": self.password},
                    format="json",
                )
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_email", response.data)

    def test_five_wrong_verifications_exhaust_code(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        wrong = "000000" if code != "000000" else "999999"
        for attempt in range(5):
            self.assertEqual(
                self.client.post(
                    self.base_url + "confirm/",
                    {"code": wrong, "password": self.password},
                    format="json",
                ).status_code,
                400,
                attempt,
            )
        record = EmailChange.objects.get(user=user)
        self.assertEqual(record.attempts, 5)
        self.assertEqual(
            self.client.post(
                self.base_url + "confirm/",
                {"code": code, "password": self.password},
                format="json",
            ).status_code,
            400,
        )

    def test_code_expires_after_fifteen_minutes(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        expiry = EmailChange.objects.get(user=user).expires_at
        with patch("django.utils.timezone.now", return_value=expiry):
            response = self.client.post(
                self.base_url + "confirm/",
                {"code": code, "password": self.password},
                format="json",
            )
        self.assertEqual(response.status_code, 400)

    def test_reissue_resets_expiry_and_old_code(self):
        user = self.create_user()
        self.login(user)
        with patch("core.email_change.services.secrets.randbelow", return_value=123456):
            previous = self.request_code()
        record = EmailChange.objects.get(user=user)
        old_pk, old_expiry = record.pk, record.expires_at
        record.used = True
        record.save(update_fields=["used"])
        cache.clear()
        with patch(
            "django.utils.timezone.now",
            return_value=timezone.now() + timedelta(minutes=1),
        ):
            with patch(
                "core.email_change.services.secrets.randbelow", return_value=654321
            ):
                current = self.request_code()
        record = EmailChange.objects.get(user=user)
        self.assertNotEqual(record.pk, old_pk)
        self.assertGreater(record.expires_at, old_expiry)
        self.assertFalse(record.used)
        self.assertEqual(record.attempts, 0)
        self.assertEqual(
            self.client.post(
                self.base_url + "confirm/",
                {"code": previous, "password": self.password},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.base_url + "confirm/",
                {"code": current, "password": self.password},
                format="json",
            ).status_code,
            200,
        )


class EmailChangeDeliveryFailureTests(ApiTransactionCase):
    def test_delivery_failure_is_uniform_without_new_code(self):
        user = self.create_user()
        self.login(user)
        with patch(
            "core.email_change.services.send_email_token",
            side_effect=RuntimeError("mail down"),
        ):
            response = self.client.post(
                "/api/email-change/request/",
                {"new_email": "new@example.com", "password": self.password},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(EmailChange.objects.filter(user=user).exists())


class EmailChangeAttemptPersistenceTests(ApiTransactionCase):
    def test_failed_confirmation_persists_attempt_after_400(self):
        user = self.create_user()
        self.login(user)
        self.assertEqual(
            self.client.post(
                "/api/email-change/request/",
                {"new_email": "new@example.com", "password": self.password},
                format="json",
            ).status_code,
            200,
        )
        code = self.email_code()
        wrong = "000000" if code != "000000" else "999999"
        response = self.client.post(
            "/api/email-change/confirm/",
            {"code": wrong, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmailChange.objects.get(user=user).attempts, 1)
