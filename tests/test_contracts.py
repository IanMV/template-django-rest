from django.db import connections
from django.urls import URLPattern, URLResolver, get_resolver, resolve

from tests.base import ApiCase


class ContractTests(ApiCase):
    def test_codes_require_six_ascii_digits_before_service_calls(self):
        from core.email_change.serializers import EmailChangeConfirmSerializer
        from core.password_reset.serializers import PasswordResetConfirmSerializer
        from core.registration.serializers import RegistrationConfirmSerializer

        for serializer_class in (
            RegistrationConfirmSerializer,
            PasswordResetConfirmSerializer,
            EmailChangeConfirmSerializer,
        ):
            for code in ("", "12345", "1234567", "abcdef", "１２３４５６", "١٢٣٤٥٦"):
                with self.subTest(serializer=serializer_class.__name__, code=code):
                    serializer = serializer_class(
                        data={
                            "email": "test@example.com",
                            "name": "Example Person",
                            "password": self.password,
                            "new_password": self.password,
                            "code": code,
                        }
                    )
                    self.assertFalse(serializer.is_valid())
                    self.assertIn("code", serializer.errors)

    def test_all_protected_routes_require_authentication(self):
        protected = {
            "logout": ("post", "/api/me/logout/"),
            "deactivate-self": ("post", "/api/me/deactivate/"),
            "email-change-request": ("post", "/api/email-change/request/"),
            "email-change-confirm": ("post", "/api/email-change/confirm/"),
            "me": ("get", "/api/users/me/"),
            "users-list": ("get", "/api/users/list/"),
        }

        def named(patterns, prefix=""):
            for pattern in patterns:
                path = prefix + str(pattern.pattern)
                if isinstance(pattern, URLResolver):
                    yield from named(pattern.url_patterns, path)
                elif (
                    isinstance(pattern, URLPattern)
                    and pattern.name
                    and path.startswith("api/")
                ):
                    yield pattern.name

        public = {
            "login",
            "registration-request",
            "registration-confirm",
            "password-reset-request",
            "password-reset-confirm",
            "schema",
            "swagger-ui",
        }
        self.assertEqual(
            set(named(get_resolver().url_patterns)) - public, set(protected)
        )
        for name, (method, path) in protected.items():
            with self.subTest(name=name):
                self.assertEqual(resolve(path).url_name, name)
                self.assertEqual(
                    getattr(self.client, method)(path, {}, format="json").status_code,
                    401,
                )

    def test_removed_routes_are_not_available(self):
        self.login(self.create_user())
        for path in (
            "/api/refresh/",
            "/api/sessions/",
            "/api/me/revoke-sessions/",
            "/api/audit/",
            "/api/registration/verify/",
            "/api/password-reset/verify/",
            "/api/email-change/verify/",
            "/manual/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_unrouted_user_detail_and_update_remain_unavailable(self):
        user = self.create_user()
        self.login(user)
        self.assertEqual(self.client.get(f"/api/users/{user.pk}/").status_code, 404)
        self.assertEqual(
            self.client.patch(
                "/api/users/me/", {"name": "new"}, format="json"
            ).status_code,
            405,
        )

    def test_schema_describes_csrf_and_session_contract(self):
        schema = self.client.get("/api/docs/schema/?format=json").json()
        login = schema["paths"]["/api/login/"]["post"]
        self.assertEqual(login["security"], [{"csrfHeader": []}])
        profile = schema["paths"]["/api/users/me/"]["get"]
        self.assertEqual(profile["security"], [{"sessionCookie": []}])
        logout = schema["paths"]["/api/me/logout/"]["post"]
        self.assertEqual(logout["security"], [{"sessionCookie": [], "csrfHeader": []}])
        for path in (
            "/api/email-change/request/",
            "/api/email-change/confirm/",
            "/api/me/deactivate/",
        ):
            operation = schema["paths"][path]["post"]
            self.assertIn("429", operation["responses"])
            self.assertIn("503", operation["responses"])
            component = operation["requestBody"]["content"]["application/json"][
                "schema"
            ]["$ref"].split("/")[-1]
            self.assertIn(
                "password", schema["components"]["schemas"][component]["required"]
            )
        self.assertNotIn("/api/refresh/", schema["paths"])

    def test_atomic_requests_is_disabled(self):
        self.assertFalse(connections["default"].settings_dict["ATOMIC_REQUESTS"])
