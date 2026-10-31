from django.conf import settings
from django.db import connections
from django.test import override_settings
from django.urls import URLPattern, URLResolver, get_resolver, resolve

from tests.base import ApiCase


class ContractTests(ApiCase):
    def test_all_protected_routes_require_authentication(self):
        protected = {
            "logout": ("post", "/api/me/logout/"),
            "deactivate-self": ("post", "/api/me/deactivate/"),
            "revoke-sessions": ("post", "/api/me/revoke-sessions/"),
            "user-sessions-list": ("get", "/api/sessions/"),
            "user-sessions-deactivate": ("delete", "/api/sessions/999/"),
            "email-change-request": ("post", "/api/email-change/request/"),
            "email-change-verify": ("post", "/api/email-change/verify/"),
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
            "refresh",
            "registration-request",
            "registration-verify",
            "registration-confirm",
            "password-reset-request",
            "password-reset-verify",
            "password-reset-confirm",
            "schema",
            "swagger-ui",
        }
        names = set(named(get_resolver().url_patterns))
        self.assertEqual(names - public, set(protected))
        for name, (method, path) in protected.items():
            with self.subTest(name=name):
                self.assertEqual(resolve(path).url_name, name)
                self.assertEqual(
                    getattr(self.client, method)(path, {}, format="json").status_code,
                    401,
                )

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

    def test_user_list_requires_staff_and_is_paginated(self):
        user = self.create_user()
        self.login(user)
        self.assertEqual(self.client.get("/api/users/list/").status_code, 403)
        staff = self.create_user(email="staff@example.com", is_staff=True)
        self.login(staff)
        response = self.client.get("/api/users/list/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 2)

    def test_reauthentication_contract_is_documented(self):
        schema = self.client.get("/api/docs/schema/?format=json").json()
        for path in ("/api/email-change/request/", "/api/me/deactivate/"):
            operation = schema["paths"][path]["post"]
            self.assertIn("429", operation["responses"])
            self.assertIn("503", operation["responses"])
            component = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
            self.assertIn("password", schema["components"]["schemas"][component]["required"])

    def test_other_session_deletion_does_not_require_password(self):
        user = self.create_user()
        self.login(user)
        other = self.new_client()
        self.login(user, client=other, ip="127.0.0.2")
        sessions = self.client.get("/api/sessions/").data
        target = next(session["id"] for session in sessions if not session["current"])
        self.assertEqual(self.client.delete(f"/api/sessions/{target}/").status_code, 200)

    def test_atomic_requests_is_disabled(self):
        self.assertFalse(connections["default"].settings_dict["ATOMIC_REQUESTS"])

    def test_canonical_models_are_exported_from_package(self):
        from core.models import (
            EmailChange,
            EmailVerification,
            OneTimeCode,
            PasswordReset,
            UserSession,
        )

        self.assertEqual(UserSession._meta.app_label, "core")
        self.assertEqual(EmailVerification._meta.app_label, "core")
        self.assertTrue(OneTimeCode._meta.abstract)
        self.assertEqual(PasswordReset._meta.app_label, "core")
        self.assertEqual(EmailChange._meta.app_label, "core")

    def test_cookie_names_and_flags_match_public_contract(self):
        user = self.create_user()
        _, response = self.login(user)
        for name in ("access_token", "refresh_token"):
            self.assertTrue(response.cookies[name]["httponly"])
            self.assertEqual(response.cookies[name]["samesite"], "Lax")
            self.assertFalse(response.cookies[name]["secure"])
        self.assertEqual(response.cookies["access_token"]["path"], "/")
        self.assertEqual(response.cookies["refresh_token"]["path"], "/api/refresh/")
        self.assertIn("Path=/", response["Set-Cookie"])
        self.assertIn("Max-Age=0", response["Set-Cookie"])

    @override_settings(
        SIMPLE_JWT={**settings.SIMPLE_JWT, "AUTH_COOKIE": "custom_access"}
    )
    def test_access_cookie_name_is_configurable_but_refresh_is_fixed(self):
        user = self.create_user()
        _, response = self.login(user)
        self.assertIn("custom_access", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertNotIn("access_token", response.cookies)
        self.assertEqual(self.client.get("/api/users/me/").status_code, 200)

    @override_settings(
        SIMPLE_JWT={**settings.SIMPLE_JWT, "AUTH_COOKIE_SECURE": True},
        CSRF_COOKIE_SECURE=True,
    )
    def test_secure_cookies_under_production_flags(self):
        user = self.create_user()
        _, response = self.login(user)
        self.assertTrue(response.cookies["access_token"]["secure"])
        self.assertTrue(response.cookies["refresh_token"]["secure"])
        self.assertTrue(response.cookies["csrftoken"]["secure"])

    def test_schema_endpoint_is_available(self):
        self.assertEqual(self.client.get("/api/docs/schema/").status_code, 200)
