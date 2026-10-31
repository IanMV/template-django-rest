from datetime import timedelta

from django.conf import settings
from django.core.cache import caches
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from core.models.user import UserSession
from tests.base import ApiCase


class RememberMeTests(ApiCase):
    def test_standard_login_retains_one_day_refresh_and_thirty_day_absolute(self):
        user = self.create_user()
        _, response = self.login(user)
        session = UserSession.objects.get(user=user)
        self.assertFalse(session.remember_me)
        self.assertEqual(int(response.cookies["refresh_token"]["max-age"]), 86400)
        self.assertEqual(list(response.data), ["detail"])
        self.assertEqual(settings.SESSION_ABSOLUTE_LIFETIME, timedelta(days=30))

    def test_remembered_login_refresh_and_reuse(self):
        user = self.create_user()
        _, response = self.login(user, remember_me=True)
        session = UserSession.objects.get(user=user)
        self.assertTrue(session.remember_me)
        self.assertEqual(int(response.cookies["refresh_token"]["max-age"]), 7 * 86400)
        old = response.cookies["refresh_token"].value
        old_jti = RefreshToken(old)["jti"]
        self.assertEqual(
            OutstandingToken.objects.get(jti=old_jti).token, old
        )
        with self.captureOnCommitCallbacks(execute=True):
            rotated = self.client.post("/api/refresh/")
        self.assertEqual(rotated.status_code, 200, rotated.data)
        self.assertEqual(list(rotated.data), ["detail"])
        session.refresh_from_db()
        self.assertTrue(session.remember_me)
        new = rotated.cookies["refresh_token"].value
        self.assertEqual(
            OutstandingToken.objects.get(jti=session.refresh_jti).token, new
        )
        self.assertEqual(int(rotated.cookies["refresh_token"]["max-age"]), 7 * 86400)
        self.assertEqual(RefreshToken(new)["session_id"], session.pk)
        self.assertEqual(AccessToken(rotated.cookies["access_token"].value)["session_id"], session.pk)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=old_jti).exists())
        self.client.cookies["refresh_token"] = old
        with self.captureOnCommitCallbacks(execute=True):
            reused = self.client.post("/api/refresh/")
        self.assertEqual(reused.status_code, 401)
        session.refresh_from_db()
        self.assertFalse(session.is_active)

    def test_refresh_caps_expiry_and_cookie_at_absolute_limit(self):
        user = self.create_user()
        self.login(user, remember_me=True)
        session = UserSession.objects.get(user=user)
        cutoff = timezone.now() - settings.SESSION_REMEMBERED_ABSOLUTE_LIFETIME + timedelta(hours=1)
        UserSession.objects.filter(pk=session.pk).update(created_at=cutoff)
        rotated = self.client.post("/api/refresh/")
        self.assertEqual(rotated.status_code, 200)
        refresh = RefreshToken(rotated.cookies["refresh_token"].value)
        access = AccessToken(rotated.cookies["access_token"].value)
        self.assertLessEqual(refresh["exp"], int((cutoff + settings.SESSION_REMEMBERED_ABSOLUTE_LIFETIME).timestamp()))
        self.assertLessEqual(access["exp"], refresh["exp"])
        self.assertLessEqual(int(rotated.cookies["refresh_token"]["max-age"]), 3600)
        self.assertGreater(int(rotated.cookies["refresh_token"]["max-age"]), 0)

    def test_access_and_refresh_both_stop_at_absolute_limit(self):
        user = self.create_user()
        self.login(user, remember_me=True)
        session = UserSession.objects.get(user=user)
        cutoff = timezone.now() - settings.SESSION_REMEMBERED_ABSOLUTE_LIFETIME + timedelta(minutes=5)
        UserSession.objects.filter(pk=session.pk).update(created_at=cutoff)
        response = self.client.post("/api/refresh/")
        self.assertEqual(response.status_code, 200)
        expiry = int((cutoff + settings.SESSION_REMEMBERED_ABSOLUTE_LIFETIME).timestamp())
        self.assertLessEqual(AccessToken(response.cookies["access_token"].value)["exp"], expiry)
        self.assertLessEqual(RefreshToken(response.cookies["refresh_token"].value)["exp"], expiry)
        self.assertLessEqual(int(response.cookies["access_token"]["max-age"]), 300)

    def test_remembered_refresh_invalidates_old_access_cache(self):
        user = self.create_user()
        self.login(user, remember_me=True)
        session = UserSession.objects.get(user=user)
        old_access = self.client.cookies["access_token"].value
        self.assertEqual(self.client.get("/api/users/me/").status_code, 200)
        key = f"session:{session.pk}"
        self.assertIsNotNone(caches["sessions"].get(key))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post("/api/refresh/").status_code, 200)
        self.assertIsNone(caches["sessions"].get(key))
        self.client.cookies["access_token"] = old_access
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_new_login_replaces_flag_on_same_device(self):
        user = self.create_user()
        self.login(user, remember_me=True)
        previous = UserSession.objects.get(user=user, is_active=True)
        _, response = self.login(user)
        previous.refresh_from_db()
        self.assertFalse(previous.is_active)
        replacement = UserSession.objects.get(user=user, is_active=True)
        self.assertFalse(replacement.remember_me)
        self.assertEqual(int(response.cookies["refresh_token"]["max-age"]), 86400)

    def test_expired_absolute_limit_returns_401_and_clears_cookies(self):
        user = self.create_user()
        self.login(user, remember_me=True)
        session = UserSession.objects.get(user=user)
        UserSession.objects.filter(pk=session.pk).update(
            created_at=timezone.now() - settings.SESSION_REMEMBERED_ABSOLUTE_LIFETIME
        )
        response = self.client.post("/api/refresh/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.cookies["refresh_token"]["max-age"], 0)
        session.refresh_from_db()
        self.assertFalse(session.is_active)
