from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from core.models.user import UserSession
from tests.base import ApiCase


class AuthenticationTests(ApiCase):
    def test_login_bootstraps_csrf_cookie(self):
        response = self.client.get("/api/login/")
        self.assertEqual(response.status_code, 204)
        self.assertIn("csrftoken", response.cookies)

    def test_login_requires_csrf_header(self):
        user = self.create_user()
        self.client.get("/api/login/")
        response = self.client.post(
            "/api/login/",
            {"email": user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(UserSession.objects.exists())

    def test_login_returns_detail_and_httponly_cookies(self):
        user = self.create_user()
        _, response = self.login(user)
        self.assertEqual(list(response.data), ["detail"])
        for name in ("access_token", "refresh_token"):
            self.assertIn(name, response.cookies)
            self.assertTrue(response.cookies[name]["httponly"])
            self.assertEqual(response.cookies[name]["samesite"], "Lax")

    def test_login_rejects_invalid_credentials(self):
        user = self.create_user()
        self.client.get("/api/login/")
        self.client.credentials(HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        response = self.client.post(
            "/api/login/", {"email": user.email, "password": "wrong"}, format="json"
        )
        self.assertEqual(response.status_code, 401, response.data)
        self.assertFalse(UserSession.objects.exists())

    def test_login_revokes_previous_cookie_session_even_for_different_user(self):
        first = self.create_user()
        second = self.create_user(email="second@example.com")
        self.login(first)
        first_session = UserSession.objects.get(user=first)
        self.login(second)
        first_session.refresh_from_db()
        self.assertFalse(first_session.is_active)
        self.assertEqual(
            UserSession.objects.filter(user=second, is_active=True).count(), 1
        )

    def test_login_replaces_same_user_device_and_ip(self):
        user = self.create_user()
        self.login(user)
        previous = UserSession.objects.get(user=user)
        previous_refresh = previous.refresh_jti
        self.login(user)
        previous.refresh_from_db()
        self.assertFalse(previous.is_active)
        self.assertEqual(
            UserSession.objects.filter(user=user, is_active=True).count(), 1
        )
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=previous_refresh).exists()
        )

    def test_inactive_session_rejects_valid_access_token(self):
        user = self.create_user()
        self.login(user)
        UserSession.objects.filter(user=user).update(is_active=False)
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_authenticated_unsafe_request_requires_csrf(self):
        user = self.create_user()
        self.login(user)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/me/logout/").status_code, 403)


class RefreshTests(ApiCase):
    def test_refresh_requires_csrf_when_access_cookie_is_expired(self):
        user = self.create_user()
        self.login(user)
        expired = AccessToken(self.client.cookies["access_token"].value)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        self.client.cookies["access_token"] = str(expired)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/refresh/").status_code, 403)

    def test_refresh_rotates_both_jtis_and_updates_activity(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        old_access, old_refresh = session.access_jti, session.refresh_jti
        next_activity = timezone.now() + timedelta(minutes=1)
        with patch("django.utils.timezone.now", return_value=next_activity):
            response = self.client.post("/api/refresh/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(response.data), ["detail"])
        session.refresh_from_db()
        self.assertNotEqual(session.access_jti, old_access)
        self.assertNotEqual(session.refresh_jti, old_refresh)
        self.assertEqual(session.last_activity, next_activity)
        self.assertEqual(
            AccessToken(response.cookies["access_token"].value)["jti"],
            session.access_jti,
        )
        self.assertEqual(
            RefreshToken(response.cookies["refresh_token"].value)["jti"],
            session.refresh_jti,
        )
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=old_refresh).exists()
        )

    def test_old_refresh_cookie_cannot_revive_rotated_session(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        old = self.client.cookies["refresh_token"].value
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post("/api/refresh/").status_code, 200)
        current = self.client.cookies["refresh_token"].value
        self.client.cookies["refresh_token"] = old
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/refresh/")
        self.assertEqual(response.status_code, 401)
        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.client.cookies["refresh_token"] = current
        self.assertEqual(self.client.post("/api/refresh/").status_code, 401)

    def test_absolute_lifetime_revokes_session_and_clears_cookies(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        UserSession.objects.filter(pk=session.pk).update(
            created_at=timezone.now() - settings.SESSION_ABSOLUTE_LIFETIME
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/refresh/")
        self.assertEqual(response.status_code, 401)
        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.assertEqual(response.cookies["access_token"]["max-age"], 0)
        self.assertEqual(response.cookies["refresh_token"]["max-age"], 0)

    def test_session_within_absolute_lifetime_can_refresh(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        UserSession.objects.filter(pk=session.pk).update(
            created_at=timezone.now() - settings.SESSION_ABSOLUTE_LIFETIME + timedelta(days=1)
        )
        self.assertEqual(self.client.post("/api/refresh/").status_code, 200)

    def test_revoked_session_cannot_refresh(self):
        user = self.create_user()
        self.login(user)
        UserSession.objects.filter(user=user).update(is_active=False)
        self.assertEqual(self.client.post("/api/refresh/").status_code, 401)

    def test_inactive_user_cannot_refresh(self):
        user = self.create_user()
        self.login(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertEqual(self.client.post("/api/refresh/").status_code, 401)
