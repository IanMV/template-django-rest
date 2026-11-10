from django.conf import settings
from django.test import override_settings

from tests.base import ApiCase


class HttpFlowTests(ApiCase):
    """HTTP cookie/CSRF flows, not a browser engine or a CORS enforcement emulator."""

    def test_every_public_mutation_requires_csrf(self):
        fresh = self.new_client()
        for path in (
            "login/",
            "registration/request/",
            "registration/confirm/",
            "password-reset/request/",
            "password-reset/confirm/",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    fresh.post(f"/api/{path}", {}, format="json").status_code, 403
                )

    def test_signup_login_reload_logout_with_cookie_jar_and_json_csrf(self):
        client = self.new_client()
        self.bootstrap(client)
        email = "new@example.com"
        response = client.post(
            "/api/registration/request/", {"email": email}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        response = client.post(
            "/api/registration/confirm/",
            {
                "email": email,
                "code": self.email_code(),
                "name": "New Person",
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get("/api/users/me/").status_code, 401)
        response = client.post(
            "/api/login/", {"email": email, "password": self.password}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("sessionid", response.data)
        self.assertEqual(client.get("/api/users/me/").data["email"], email)
        # Reload loses in-memory CSRF, but the cookie jar still identifies the session.
        client.credentials()
        self.assertEqual(client.post("/api/me/logout/").status_code, 403)
        self.bootstrap(client)
        self.assertEqual(client.post("/api/me/logout/").status_code, 200)
        self.assertEqual(client.get("/api/users/me/").status_code, 401)

    def test_forged_and_mismatched_csrf_tokens_are_rejected(self):
        user = self.create_user()
        self.login(user)
        for token in ("invalid", "a" * 64):
            self.client.credentials(HTTP_X_CSRFTOKEN=token)
            self.assertEqual(self.client.post("/api/me/logout/").status_code, 403)

    @override_settings(
        CORS_ALLOWED_ORIGINS=["http://localhost:5173"],
        CSRF_TRUSTED_ORIGINS=["http://localhost:5173"],
    )
    def test_trusted_origin_preflight_and_credentialed_login(self):
        origin = "http://localhost:5173"
        response = self.client.options(
            "/api/login/",
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken",
        )
        self.assertEqual(response["Access-Control-Allow-Origin"], origin)
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")
        self.assertIn("x-csrftoken", response["Access-Control-Allow-Headers"])
        user = self.create_user()
        response = self.client.post(
            "/api/login/",
            {"email": user.email, "password": self.password},
            format="json",
            HTTP_ORIGIN=origin,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], origin)

    def test_untrusted_origin_rejected_even_with_valid_csrf(self):
        user = self.create_user()
        response = self.client.post(
            "/api/login/",
            {"email": user.email, "password": self.password},
            format="json",
            HTTP_ORIGIN="https://attacker.invalid",
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Access-Control-Allow-Origin", response)

    @override_settings(
        SESSION_COOKIE_NAME="__Host-sessionid",
        CSRF_COOKIE_NAME="__Host-csrftoken",
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="None",
        CSRF_COOKIE_SAMESITE="None",
    )
    def test_https_cookie_flags_are_emitted(self):
        user = self.create_user()
        self.client.credentials()
        response = self.client.get("/api/login/", secure=True)
        response = self.client.post(
            "/api/login/",
            {"email": user.email, "password": self.password},
            format="json",
            secure=True,
            HTTP_X_CSRFTOKEN=response.data["csrfToken"],
            HTTP_REFERER="https://testserver/",
        )
        self.assertEqual(response.status_code, 200)
        for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
            cookie = response.cookies[name]
            self.assertTrue(cookie["secure"])
            self.assertTrue(cookie["httponly"])
            self.assertEqual(cookie["samesite"], "None")
            self.assertEqual(cookie["path"], "/")
            self.assertFalse(cookie["domain"])
