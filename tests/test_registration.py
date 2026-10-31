from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.utils import timezone

from core.models.email_verification import EmailVerification
from core.models.user import User
from tests.base import ApiCase, ApiTransactionCase


class RegistrationTests(ApiCase):
    email = "new@example.com"
    base_url = "/api/registration/"

    def request_code(self):
        response = self.post_with_commit(self.base_url + "request/", {"email": self.email})
        self.assertEqual(response.status_code, 201, response.data)
        return self.email_code()

    def test_request_sends_hashed_code_to_inactive_user(self):
        code = self.request_code()
        record = EmailVerification.objects.get(user__email=self.email)
        self.assertFalse(record.user.is_active)
        self.assertNotEqual(record.code, code)
        self.assertEqual(mail.outbox[-1].to, [self.email])

    def test_active_account_gets_same_response_and_security_notice(self):
        active = self.create_user(email="active@example.com")
        first = self.post_with_commit(
            self.base_url + "request/", {"email": active.email}
        )
        self.assertEqual(first.status_code, 201)
        self.assertFalse(EmailVerification.objects.filter(user=active).exists())
        self.assertEqual(mail.outbox[-1].to, [active.email])
        self.assertNotIn("Your code is:", mail.outbox[-1].body)
        cache.clear()
        second = self.post_with_commit(
            self.base_url + "request/", {"email": self.email}
        )
        self.assertEqual((first.status_code, first.data), (second.status_code, second.data))

    def test_verify_does_not_consume_and_confirm_creates_active_user(self):
        code = self.request_code()
        payload = {"email": self.email, "code": code}
        self.assertEqual(
            self.client.post(
                self.base_url + "verify/", payload, format="json"
            ).status_code,
            200,
        )
        record = EmailVerification.objects.get(user__email=self.email)
        self.assertFalse(record.used)
        response = self.client.post(
            self.base_url + "confirm/",
            {**payload, "name": "Example Person", "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        user = User.objects.get(email=self.email)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(self.password))
        record.refresh_from_db()
        self.assertTrue(record.used)
        self.assertEqual(
            self.client.post(
                self.base_url + "confirm/",
                {**payload, "name": "Example Person", "password": self.password},
                format="json",
            ).status_code,
            400,
        )

    def test_five_wrong_verifications_exhaust_code(self):
        code = self.request_code()
        for attempt in range(5):
            response = self.client.post(
                self.base_url + "verify/",
                {
                    "email": self.email,
                    "code": "000000" if code != "000000" else "999999",
                },
                format="json",
            )
            self.assertEqual(response.status_code, 400, attempt)
        record = EmailVerification.objects.get(user__email=self.email)
        self.assertEqual(record.attempts, 5)
        self.assertTrue(record.used)
        self.assertEqual(
            self.client.post(
                self.base_url + "verify/",
                {"email": self.email, "code": code},
                format="json",
            ).status_code,
            400,
        )

    def test_code_expires_after_fifteen_minutes(self):
        code = self.request_code()
        record = EmailVerification.objects.get(user__email=self.email)
        with patch("django.utils.timezone.now", return_value=record.expires_at):
            response = self.client.post(
                self.base_url + "verify/",
                {"email": self.email, "code": code},
                format="json",
            )
        self.assertEqual(response.status_code, 400)

    def test_reissue_replaces_old_code_and_resets_expiry_and_usage(self):
        previous = self.request_code()
        record = EmailVerification.objects.get(user__email=self.email)
        old_pk, old_expiry = record.pk, record.expires_at
        record.used = True
        record.save(update_fields=["used"])
        cache.clear()
        with patch(
            "django.utils.timezone.now",
            return_value=timezone.now() + timedelta(minutes=1),
        ):
            current = self.request_code()
        record = EmailVerification.objects.get(user__email=self.email)
        self.assertNotEqual(record.pk, old_pk)
        self.assertGreater(record.expires_at, old_expiry)
        self.assertFalse(record.used)
        self.assertEqual(record.attempts, 0)
        self.assertEqual(
            self.client.post(
                self.base_url + "verify/",
                {"email": self.email, "code": previous},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.base_url + "verify/",
                {"email": self.email, "code": current},
                format="json",
            ).status_code,
            200,
        )

    def test_password_similarity_is_rejected(self):
        code = self.request_code()
        response = self.client.post(
            self.base_url + "confirm/",
            {
                "email": self.email,
                "code": code,
                "name": "Example Person",
                "password": "Example Person",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.get(email=self.email).is_active)

class RegistrationDeliveryFailureTests(ApiTransactionCase):
    def test_delivery_failure_returns_503_and_rolls_back_new_user(self):
        email = "new@example.com"
        with patch(
            "core.registration.services.send_email_token",
            side_effect=RuntimeError("mail down"),
        ):
            response = self.client.post(
                "/api/registration/request/", {"email": email}, format="json"
            )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(User.objects.filter(email=email).exists())


class RegistrationAttemptPersistenceTests(ApiTransactionCase):
    def test_failed_confirmation_commits_attempt_even_on_400(self):
        email = "new@example.com"
        self.assertEqual(
            self.client.post(
                "/api/registration/request/", {"email": email}, format="json"
            ).status_code,
            201,
        )
        correct = self.email_code()
        wrong = "000000" if correct != "000000" else "999999"
        response = self.client.post(
            "/api/registration/confirm/",
            {
                "email": email,
                "code": wrong,
                "name": "Example Person",
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmailVerification.objects.get(user__email=email).attempts, 1)
