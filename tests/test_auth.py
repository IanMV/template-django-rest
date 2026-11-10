from django.conf import settings
from django.contrib.sessions.models import Session

from tests.base import ApiCase


class AuthenticationTests(ApiCase):
    def test_bootstrap_returns_only_csrf_and_cannot_be_cached(self):
        response = self.bootstrap(self.client)
        self.assertEqual(set(response.data), {"csrfToken"})
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(response.cookies[settings.CSRF_COOKIE_NAME]["httponly"])
        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)

    def test_login_rotates_csrf_and_sets_opaque_session_cookie(self):
        user = self.create_user()
        previous = self.bootstrap(self.client).data["csrfToken"]
        _, response = self.login(user)
        self.assertEqual(set(response.data), {"detail", "csrfToken"})
        self.assertNotEqual(previous, response.data["csrfToken"])
        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], "/")
        self.assertLessEqual(int(cookie["max-age"]), 86400)
        self.assertGreater(int(cookie["max-age"]), 86390)
        self.assertTrue(Session.objects.filter(session_key=cookie.value).exists())
        self.client.credentials(HTTP_X_CSRFTOKEN=previous)
        self.assertEqual(self.client.post("/api/me/logout/").status_code, 403)

    def test_login_rejects_invalid_and_inactive_credentials(self):
        user = self.create_user()
        for password, active in (("wrong", True), (self.password, False)):
            user.is_active = active
            user.save()
            response = self.client.post(
                "/api/login/",
                {"email": user.email, "password": password},
                format="json",
            )
            self.assertEqual(response.status_code, 401)
            self.assertFalse(Session.objects.exists())

    def test_switching_accounts_flushes_old_session(self):
        first = self.create_user()
        second = self.create_user(email="second@example.com")
        self.login(first)
        old_key = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        replay = self.new_client()
        replay.cookies[settings.SESSION_COOKIE_NAME] = old_key
        self.login(second)
        self.assertFalse(Session.objects.filter(session_key=old_key).exists())
        self.assertEqual(replay.get("/api/users/me/").status_code, 401)
        self.assertEqual(self.client.get("/api/users/me/").data["email"], second.email)

    def test_session_fixation_is_prevented(self):
        session = self.client.session
        session["anonymous"] = True
        session.save()
        old_key = session.session_key
        self.login(self.create_user())
        self.assertNotEqual(self.client.session.session_key, old_key)
        self.assertFalse(Session.objects.filter(session_key=old_key).exists())
