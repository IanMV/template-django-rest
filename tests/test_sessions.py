from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken

from core.models.user import UserSession
from tests.base import ApiCase


class SessionTests(ApiCase):
    def test_logout_revokes_current_session_and_deletes_cookies(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        response = self.client.post("/api/me/logout/")
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=session.refresh_jti).exists()
        )
        for name in ("access_token", "refresh_token"):
            self.assertEqual(response.cookies[name]["max-age"], 0)
        self.assertEqual(response.cookies["refresh_token"]["path"], "/api/refresh/")
        self.assertIn("refresh_token=", response["Set-Cookie"])
        self.assertIn("Path=/", response["Set-Cookie"])
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_logout_without_refresh_cookie_still_revokes_session(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        self.client.get("/api/users/me/")
        del self.client.cookies["refresh_token"]
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/me/logout/")
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_revoke_all_without_refresh_cookie_still_revokes_session(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        self.client.get("/api/users/me/")
        del self.client.cookies["refresh_token"]
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/me/revoke-sessions/")
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_session_list_marks_only_current_session(self):
        user = self.create_user()
        self.login(user)
        other = self.new_client()
        self.login(user, client=other, ip="127.0.0.2")
        response = self.client.get("/api/sessions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(sum(item["current"] for item in response.data), 1)

    def test_cannot_deactivate_current_session(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        response = self.client.delete(f"/api/sessions/{session.pk}/")
        self.assertEqual(response.status_code, 400)
        session.refresh_from_db()
        self.assertTrue(session.is_active)

    def test_legacy_access_token_marks_current_and_cannot_delete_it(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        token = AccessToken(self.client.cookies["access_token"].value)
        del token["session_id"]
        self.client.cookies["access_token"] = str(token)
        listed = self.client.get("/api/sessions/")
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(listed.data[0]["current"])
        self.assertEqual(
            self.client.delete(f"/api/sessions/{session.pk}/").status_code, 400
        )
        session.refresh_from_db()
        self.assertTrue(session.is_active)

    def test_can_deactivate_other_own_session(self):
        user = self.create_user()
        self.login(user)
        other = self.new_client()
        self.login(user, client=other, ip="127.0.0.2")
        session = UserSession.objects.get(user=user, ip_address="127.0.0.2")
        response = self.client.delete(f"/api/sessions/{session.pk}/")
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertFalse(session.is_active)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=session.refresh_jti).exists()
        )

    def test_other_users_session_is_indistinguishable_from_missing(self):
        owner = self.create_user()
        stranger = self.create_user(email="stranger@example.com")
        self.login(owner)
        other = self.new_client()
        self.login(stranger, client=other, ip="127.0.0.2")
        session = UserSession.objects.get(user=stranger)
        denied = self.client.delete(f"/api/sessions/{session.pk}/")
        absent = self.client.delete("/api/sessions/999999/")
        self.assertEqual(
            (denied.status_code, denied.data), (absent.status_code, absent.data)
        )
        self.assertEqual(denied.status_code, 404)
        session.refresh_from_db()
        self.assertTrue(session.is_active)

    def test_revoke_all_invalidates_every_device_and_clears_cookies(self):
        user = self.create_user()
        self.login(user)
        other = self.new_client()
        self.login(user, client=other, ip="127.0.0.2")
        response = self.client.post("/api/me/revoke-sessions/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserSession.objects.filter(user=user, is_active=True).exists())
        self.assertEqual(BlacklistedToken.objects.filter(token__user=user).count(), 2)
        self.assertEqual(response.cookies["access_token"]["max-age"], 0)
        self.assertEqual(response.cookies["refresh_token"]["max-age"], 0)
        self.assertEqual(other.get("/api/users/me/").status_code, 401)
