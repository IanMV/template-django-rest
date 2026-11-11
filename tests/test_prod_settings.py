import importlib
from contextlib import contextmanager
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class ProductionSettingsTests(SimpleTestCase):
    @contextmanager
    def production_settings(self, **overrides):
        values = {
            "SECRET_KEY": "synthetic-production-test-key-with-at-least-fifty-characters-12345",
            "ALLOWED_HOSTS": "api.example.com",
            "FRONTEND_ORIGINS": "https://spa.example.com",
            "DATABASE_URL": "postgresql://test:test@127.0.0.1:5432/test",
            "EMAIL_HOST": "smtp.example.com",
            "DEFAULT_FROM_EMAIL": "test@example.com",
            **overrides,
        }
        with patch(
            "os.getenv", side_effect=lambda key, default=None: values.get(key, default)
        ):
            yield importlib.reload(importlib.import_module("app.settings.prod"))

    def test_proxy_headers_require_explicit_trust(self):
        with self.production_settings() as configured:
            self.assertIsNone(configured.SECURE_PROXY_SSL_HEADER)
        with self.production_settings(TRUST_PROXY_HEADERS="true") as configured:
            self.assertEqual(
                configured.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
            )

    def test_smtp_backend_receives_finite_timeout(self):
        with self.production_settings() as configured:
            with self.settings(MAILERS=configured.MAILERS):
                self.assertEqual(mail.mailers["default"].timeout, 10)

    def test_smtp_ssl_and_starttls_are_mutually_exclusive(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "not both"):
            with self.production_settings(EMAIL_USE_SSL="true", EMAIL_USE_TLS="true"):
                pass
        with self.assertRaisesMessage(ImproperlyConfigured, "not both"):
            with self.production_settings(
                EMAIL_USE_SSL=" true ", EMAIL_USE_TLS=" TRUE "
            ):
                pass
        with self.production_settings(
            EMAIL_USE_SSL=" true ", EMAIL_USE_TLS=" false ", EMAIL_PORT="465"
        ) as configured:
            with self.settings(MAILERS=configured.MAILERS):
                self.assertTrue(mail.mailers["default"].use_ssl)
                self.assertFalse(mail.mailers["default"].use_tls)

    def test_boolean_settings_reject_invalid_values(self):
        for key in ("EMAIL_USE_TLS", "EMAIL_USE_SSL", "TRUST_PROXY_HEADERS"):
            for value in ("yes", "no", "1", "0", "", "   ", "invalid"):
                with (
                    self.subTest(key=key, value=value),
                    self.assertRaisesMessage(ImproperlyConfigured, key),
                ):
                    with self.production_settings(**{key: value}):
                        pass

    def test_email_port_rejects_invalid_values(self):
        for port in ("0", "-1", "65536", "abc", "", " "):
            with (
                self.subTest(port=port),
                self.assertRaisesMessage(ImproperlyConfigured, "EMAIL_PORT"),
            ):
                with self.production_settings(EMAIL_PORT=port):
                    pass

    def test_proxy_count_accepts_zero_and_positive(self):
        for count in ("0", "1", "3"):
            with self.production_settings(NUM_PROXIES=count) as configured:
                self.assertEqual(configured.NUM_PROXIES, int(count))

    def test_proxy_count_rejects_negative_and_malformed_values(self):
        for count in ("-1", "abc", "1.5", "", " "):
            with (
                self.subTest(count=count),
                self.assertRaisesMessage(ImproperlyConfigured, "NUM_PROXIES"),
            ):
                with self.production_settings(NUM_PROXIES=count):
                    pass

    def test_missing_or_unsafe_production_configuration_is_rejected(self):
        invalid = {
            "SECRET_KEY": ("", "short", " " * 60, "django-insecure-" + "x" * 60),
            "ALLOWED_HOSTS": ("", "*"),
            "FRONTEND_ORIGINS": (
                "",
                "http://spa.example.com",
                "https://*.example.com",
                "https://spa.example.com/",
                "https://user@spa.example.com",
                "https://spa.example.com?q=1",
            ),
            "DATABASE_URL": ("", "sqlite:///test", "postgresql://localhost/"),
            "EMAIL_HOST": ("",),
            "DEFAULT_FROM_EMAIL": ("",),
        }
        for key, values in invalid.items():
            for value in values:
                with (
                    self.subTest(key=key, value=value),
                    self.assertRaises(ImproperlyConfigured),
                ):
                    with self.production_settings(**{key: value}):
                        pass

    def test_database_url_decodes_parameters(self):
        with self.production_settings(
            DATABASE_URL="postgresql://test:pass%40word@db.internal:5433/appdb?sslmode=require"
        ) as configured:
            database = configured.DATABASES["default"]
            self.assertEqual(database["HOST"], "db.internal")
            self.assertEqual(database["PORT"], "5433")
            self.assertEqual(database["NAME"], "appdb")
            self.assertEqual(database["PASSWORD"], "pass@word")
            self.assertEqual(database["OPTIONS"], {"sslmode": "require"})

    def test_production_cookies_are_host_only_secure_and_httponly(self):
        with self.production_settings() as configured:
            for prefix in ("SESSION", "CSRF"):
                self.assertTrue(
                    getattr(configured, f"{prefix}_COOKIE_NAME").startswith("__Host-")
                )
                self.assertTrue(getattr(configured, f"{prefix}_COOKIE_HTTPONLY"))
                self.assertTrue(getattr(configured, f"{prefix}_COOKIE_SECURE"))
                self.assertEqual(
                    getattr(configured, f"{prefix}_COOKIE_SAMESITE"), "None"
                )
                self.assertIsNone(getattr(configured, f"{prefix}_COOKIE_DOMAIN", None))
            self.assertEqual(
                configured.CSRF_TRUSTED_ORIGINS, configured.CORS_ALLOWED_ORIGINS
            )
