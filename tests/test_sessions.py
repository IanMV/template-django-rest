from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from core.auth.services import SessionService
from tests.base import ApiCase


class SessionTests(ApiCase):
    def test_logout_deletes_current_session_but_not_other_device(self):
        user = self.create_user()
        self.login(user)
        other, _ = self.login(user, client=self.new_client())
        key = self.client.session.session_key
        response = self.client.post("/api/me/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]["max-age"], 0)
        self.assertFalse(Session.objects.filter(session_key=key).exists())
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)
        self.assertEqual(other.get("/api/users/me/").status_code, 200)

    def test_revocation_invalidates_every_device_without_scanning_sessions(self):
        user = self.create_user()
        self.login(user)
        other, _ = self.login(user, client=self.new_client())
        for _ in range(2):
            SessionService.revoke_all_sessions(user)
        user.refresh_from_db()
        self.assertEqual(user.session_version, 2)
        self.assertEqual(Session.objects.count(), 2)
        for client in (self.client, other):
            self.assertEqual(client.get("/api/users/me/").status_code, 401)

    def test_revocation_rolls_back_with_transaction(self):
        user = self.create_user()
        self.login(user)
        with self.assertRaises(RuntimeError), transaction.atomic():
            SessionService.revoke_all_sessions(user)
            raise RuntimeError("rollback")
        self.assertEqual(self.client.get("/api/users/me/").status_code, 200)

    def test_expiry_is_absolute_despite_activity(self):
        user = self.create_user()
        self.login(user)
        session = Session.objects.get(session_key=self.client.session.session_key)
        expiry = session.expire_date
        with patch(
            "django.utils.timezone.now", return_value=expiry - timedelta(seconds=1)
        ):
            response = self.client.get("/api/users/me/")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)
        session.refresh_from_db()
        self.assertEqual(session.expire_date, expiry)
        with patch("django.utils.timezone.now", return_value=expiry):
            self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_admin_login_has_same_absolute_expiry(self):
        user = self.create_user(is_staff=True)
        response = self.client.post(
            "/admin/login/",
            {"username": user.email, "password": self.password},
            HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value,
        )
        self.assertEqual(response.status_code, 302)
        remaining = self.client.session.get_expiry_date() - timezone.now()
        self.assertAlmostEqual(remaining.total_seconds(), 86400, delta=5)

    def test_tampered_or_missing_session_never_authenticates(self):
        self.login(self.create_user())
        key = self.client.session.session_key
        Session.objects.filter(session_key=key).update(session_data="tampered")
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = "unknown"
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)
