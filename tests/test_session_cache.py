from unittest.mock import patch

from django.core.cache import caches
from django.test import override_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from core.models.user import UserSession
from tests.base import ApiCase


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SessionCacheTests(ApiCase):
    def test_malformed_session_claim_is_rejected(self):
        user = self.create_user()
        self.login(user)
        original = AccessToken(self.client.cookies["access_token"].value)
        for session_id in ("malformed", 1.5, True, 0, -1):
            with self.subTest(session_id=session_id):
                token = AccessToken(str(original))
                token["session_id"] = session_id
                self.client.cookies["access_token"] = str(token)
                self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_miss_queries_session_and_populates_cache_then_hit_skips_it(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        key = f"session:{session.pk}"
        self.assertIsNone(caches["sessions"].get(key))
        with self.assertNumQueries(2):
            self.assertEqual(self.client.get("/api/users/me/").status_code, 200)
        self.assertEqual(caches["sessions"].get(key), (session.access_jti, str(user.pk)))
        with self.assertNumQueries(1):
            self.assertEqual(self.client.get("/api/users/me/").status_code, 200)

    def test_cache_read_failure_falls_back_to_database(self):
        user = self.create_user()
        self.login(user)
        with patch.object(caches["sessions"], "get", side_effect=RuntimeError("down")):
            with self.assertLogs("core.auth.session_cache", level="ERROR"):
                with self.assertNumQueries(2):
                    self.assertEqual(self.client.get("/api/users/me/").status_code, 200)

    def test_cache_write_failure_still_authenticates_from_database(self):
        user = self.create_user()
        self.login(user)
        with patch.object(caches["sessions"], "set", side_effect=RuntimeError("down")):
            with self.assertLogs("core.auth.session_cache", level="ERROR"):
                self.assertEqual(self.client.get("/api/users/me/").status_code, 200)

    def test_cache_failure_cannot_authenticate_revoked_session(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        self.client.get("/api/users/me/")
        UserSession.objects.filter(pk=session.pk).update(is_active=False)
        with patch.object(caches["sessions"], "get", side_effect=RuntimeError("down")):
            with self.assertLogs("core.auth.session_cache", level="ERROR"):
                self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_sensitive_routes_recheck_database_despite_stale_cache_hit(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        self.client.get("/api/users/me/")
        key = f"session:{session.pk}"
        self.assertIsNotNone(caches["sessions"].get(key))
        UserSession.objects.filter(pk=session.pk).update(is_active=False)
        self.assertEqual(
            self.client.post(
                "/api/email-change/request/",
                {"new_email": "new@example.com", "password": self.password},
                format="json",
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/me/deactivate/", {"password": self.password}, format="json"
            ).status_code,
            401,
        )
        self.assertEqual(self.client.delete("/api/sessions/999999/").status_code, 401)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_wrong_binding_never_authenticates_from_cache(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        caches["sessions"].set(f"session:{session.pk}", ("wrong", str(user.pk)))
        with self.assertNumQueries(2):
            self.assertEqual(self.client.get("/api/users/me/").status_code, 200)
        self.assertEqual(
            caches["sessions"].get(f"session:{session.pk}"),
            (session.access_jti, str(user.pk)),
        )

    def test_refresh_deletes_old_binding_and_rejects_old_token(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        old_token = self.client.cookies["access_token"].value
        self.client.get("/api/users/me/")
        key = f"session:{session.pk}"
        self.assertIsNotNone(caches["sessions"].get(key))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/refresh/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(caches["sessions"].get(key))
        self.client.cookies["access_token"] = old_token
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_refresh_reuse_invalidates_new_cached_binding(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        old = self.client.cookies["refresh_token"].value
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post("/api/refresh/").status_code, 200)
        self.client.get("/api/users/me/")
        key = f"session:{session.pk}"
        self.assertIsNotNone(caches["sessions"].get(key))
        self.client.cookies["refresh_token"] = old
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post("/api/refresh/").status_code, 401)
        self.assertIsNone(caches["sessions"].get(key))

    def test_logout_invalidates_cached_session(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        self.client.get("/api/users/me/")
        del self.client.cookies["refresh_token"]
        key = f"session:{session.pk}"
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post("/api/me/logout/").status_code, 200)
        self.assertIsNone(caches["sessions"].get(key))

    def test_revoke_all_invalidates_cached_sessions(self):
        user = self.create_user()
        self.login(user)
        first = UserSession.objects.get(user=user)
        other = self.new_client()
        self.login(user, client=other, ip="127.0.0.2")
        second = UserSession.objects.get(user=user, ip_address="127.0.0.2")
        self.client.get("/api/users/me/")
        other.get("/api/users/me/")
        del self.client.cookies["refresh_token"]
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post("/api/me/revoke-sessions/").status_code, 200)
        for session in (first, second):
            self.assertIsNone(caches["sessions"].get(f"session:{session.pk}"))
        self.assertEqual(other.get("/api/users/me/").status_code, 401)

    def test_deleting_other_session_invalidates_its_cache(self):
        user = self.create_user()
        self.login(user)
        other = self.new_client()
        self.login(user, client=other, ip="127.0.0.2")
        second = UserSession.objects.get(user=user, ip_address="127.0.0.2")
        other.get("/api/users/me/")
        del self.client.cookies["refresh_token"]
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(
                self.client.delete(f"/api/sessions/{second.pk}/").status_code, 200
            )
        self.assertIsNone(caches["sessions"].get(f"session:{second.pk}"))
        self.assertEqual(other.get("/api/users/me/").status_code, 401)

    def test_login_replacement_invalidates_old_cache(self):
        user = self.create_user()
        self.login(user)
        old = UserSession.objects.get(user=user)
        old_token = self.client.cookies["access_token"].value
        self.client.get("/api/users/me/")
        del self.client.cookies["refresh_token"]
        with self.captureOnCommitCallbacks(execute=True):
            self.login(user)
        self.assertIsNone(caches["sessions"].get(f"session:{old.pk}"))
        self.client.cookies["access_token"] = old_token
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_self_deactivation_invalidates_cached_session(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        self.client.get("/api/users/me/")
        del self.client.cookies["refresh_token"]
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(
                self.client.post(
                    "/api/me/deactivate/", {"password": self.password}, format="json"
                ).status_code,
                200,
            )
        self.assertIsNone(caches["sessions"].get(f"session:{session.pk}"))

    def test_password_reset_invalidates_cached_session(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        self.client.get("/api/users/me/")
        del self.client.cookies["refresh_token"]
        self.assertEqual(
            self.post_with_commit("/api/password-reset/request/", {"email": user.email}).status_code,
            200,
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/password-reset/confirm/",
                {
                    "email": user.email,
                    "code": self.email_code(),
                    "new_password": "DifferentPass!7395",
                },
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(caches["sessions"].get(f"session:{session.pk}"))

    def test_email_change_invalidates_cached_session(self):
        user = self.create_user()
        self.login(user)
        session = UserSession.objects.get(user=user)
        self.client.get("/api/users/me/")
        del self.client.cookies["refresh_token"]
        self.assertEqual(
            self.post_with_commit(
                "/api/email-change/request/",
                {"new_email": "new@example.com", "password": self.password},
            ).status_code,
            200,
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/email-change/confirm/",
                {"code": self.email_code(), "password": self.password},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(caches["sessions"].get(f"session:{session.pk}"))

    def test_legacy_token_without_session_id_uses_database(self):
        user = self.create_user()
        self.login(user)
        token = AccessToken(self.client.cookies["access_token"].value)
        del token["session_id"]
        self.client.cookies["access_token"] = str(token)
        with self.assertNumQueries(2):
            self.assertEqual(self.client.get("/api/users/me/").status_code, 200)

    def test_refresh_upgrades_legacy_token_with_session_claim(self):
        user = self.create_user()
        self.login(user)
        old = RefreshToken(self.client.cookies["refresh_token"].value)
        del old["session_id"]
        self.client.cookies["refresh_token"] = str(old)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/refresh/")
        self.assertEqual(response.status_code, 200)
        session = UserSession.objects.get(user=user, is_active=True)
        self.assertEqual(
            AccessToken(response.cookies["access_token"].value)["session_id"],
            session.pk,
        )
