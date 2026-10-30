from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from core.models.email_change import EmailChange
from core.models.user import UserSession
from tests.base import ApiCase, ApiTransactionCase


class EmailChangeTests(ApiCase):
    base_url = "/api/email-change/"
    new_email = "new@example.com"

    def request_code(self):
        response = self.client.post(self.base_url + "request/", {"new_email": self.new_email}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return self.email_code()

    def test_request_sends_hashed_code_to_new_address(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        self.assertEqual(mail.outbox[-1].to, [self.new_email])
        self.assertNotEqual(EmailChange.objects.get(user=user).code, code)

    def test_confirm_changes_email_revokes_every_session_and_clears_cookies(self):
        user = self.create_user()
        self.login(user)
        other = self.new_client()
        self.login(user, client=other, ip="127.0.0.2")
        code = self.request_code()
        self.assertEqual(self.client.post(self.base_url + "verify/", {"code": code}, format="json").status_code, 200)
        record = EmailChange.objects.get(user=user)
        self.assertFalse(record.used)
        response = self.client.post(self.base_url + "confirm/", {"code": code, "password": self.password}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        user.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(user.email, self.new_email)
        self.assertTrue(record.used)
        self.assertFalse(UserSession.objects.filter(user=user, is_active=True).exists())
        self.assertEqual(BlacklistedToken.objects.filter(token__user=user).count(), 2)
        self.assertEqual(response.cookies["access_token"]["max-age"], 0)
        self.assertEqual(response.cookies["refresh_token"]["max-age"], 0)
        self.assertEqual(other.get("/api/users/me/").status_code, 401)
        self.login(user)
        self.assertEqual(self.client.post(self.base_url + "confirm/", {"code": code, "password": self.password}, format="json").status_code, 400)

    def test_wrong_current_password_does_not_consume_code(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        response = self.client.post(self.base_url + "confirm/", {"code": code, "password": "wrong"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(EmailChange.objects.get(user=user).used)
        user.refresh_from_db()
        self.assertNotEqual(user.email, self.new_email)

    def test_new_email_uniqueness_is_rechecked_on_confirm(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        self.create_user(email=self.new_email)
        response = self.client.post(self.base_url + "confirm/", {"code": code, "password": self.password}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_email", response.data)
        user.refresh_from_db()
        self.assertEqual(user.email, "person@example.com")

    def test_five_wrong_verifications_exhaust_code(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        wrong = "000000" if code != "000000" else "999999"
        for attempt in range(5):
            self.assertEqual(self.client.post(self.base_url + "verify/", {"code": wrong}, format="json").status_code, 400, attempt)
        record = EmailChange.objects.get(user=user)
        self.assertEqual(record.attempts, 5)
        self.assertEqual(self.client.post(self.base_url + "verify/", {"code": code}, format="json").status_code, 400)

    def test_code_expires_after_fifteen_minutes(self):
        user = self.create_user()
        self.login(user)
        code = self.request_code()
        expiry = EmailChange.objects.get(user=user).expires_at
        with patch("django.utils.timezone.now", return_value=expiry):
            response = self.client.post(self.base_url + "verify/", {"code": code}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_reissue_resets_expiry_and_old_code(self):
        user = self.create_user()
        self.login(user)
        previous = self.request_code()
        record = EmailChange.objects.get(user=user)
        old_pk, old_expiry = record.pk, record.expires_at
        record.used = True
        record.save(update_fields=["used"])
        cache.clear()
        with patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(minutes=1)):
            current = self.request_code()
        record = EmailChange.objects.get(user=user)
        self.assertNotEqual(record.pk, old_pk)
        self.assertGreater(record.expires_at, old_expiry)
        self.assertFalse(record.used)
        self.assertEqual(record.attempts, 0)
        self.assertEqual(self.client.post(self.base_url + "verify/", {"code": previous}, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.base_url + "verify/", {"code": current}, format="json").status_code, 200)

    def test_delivery_failure_returns_503_without_new_code(self):
        user = self.create_user()
        self.login(user)
        with patch("core.email_change.services.send_email_token", side_effect=RuntimeError("mail down")):
            response = self.client.post(self.base_url + "request/", {"new_email": self.new_email}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(EmailChange.objects.filter(user=user).exists())


class EmailChangeAttemptPersistenceTests(ApiTransactionCase):
    def test_failed_confirmation_persists_attempt_after_400(self):
        user = self.create_user()
        self.login(user)
        self.assertEqual(self.client.post("/api/email-change/request/", {"new_email": "new@example.com"}, format="json").status_code, 200)
        code = self.email_code()
        wrong = "000000" if code != "000000" else "999999"
        response = self.client.post("/api/email-change/confirm/", {"code": wrong, "password": self.password}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmailChange.objects.get(user=user).attempts, 1)
