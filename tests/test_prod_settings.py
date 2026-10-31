import importlib
from contextlib import contextmanager
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class ProductionSettingsTests(SimpleTestCase):
    def test_proxy_headers_require_explicit_trust(self):
        with self.production_settings() as configured:
            self.assertIsNone(configured.SECURE_PROXY_SSL_HEADER)
        with self.production_settings(TRUST_PROXY_HEADERS="true") as configured:
            self.assertEqual(
                configured.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
            )

    def test_empty_audit_retention_is_disabled(self):
        with self.production_settings(AUDIT_RETENTION_DAYS="") as configured:
            self.assertIsNone(configured.AUDIT_RETENTION_DAYS)
        with self.production_settings(AUDIT_RETENTION_DAYS="30") as configured:
            self.assertEqual(configured.AUDIT_RETENTION_DAYS, 30)

    def test_console_mail_has_no_smtp_options(self):
        with self.production_settings(
            EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
        ) as configured:
            with self.settings(MAILERS=configured.MAILERS):
                self.assertEqual(
                    type(mail.mailers["default"]).__module__,
                    "django.core.mail.backends.console",
                )
            self.assertNotIn("OPTIONS", configured.MAILERS["default"])

    def test_smtp_ssl_and_starttls_are_mutually_exclusive(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "cannot both be enabled"):
            with self.production_settings(EMAIL_USE_SSL="true", EMAIL_USE_TLS="true"):
                pass
        with self.production_settings(
            EMAIL_USE_SSL="true", EMAIL_USE_TLS="false", EMAIL_PORT="465"
        ) as configured:
            with self.settings(MAILERS=configured.MAILERS):
                self.assertTrue(mail.mailers["default"].use_ssl)
                self.assertFalse(mail.mailers["default"].use_tls)

    def test_integrated_settings_keep_real_services_and_development_cookies(self):
        with self.production_settings(
            EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
        ):
            configured = importlib.reload(
                importlib.import_module("app.settings.integrated")
            )
            self.assertTrue(configured.DEBUG)
            self.assertFalse(configured.SECURE_SSL_REDIRECT)
            self.assertFalse(configured.CSRF_COOKIE_SECURE)
            self.assertFalse(configured.SESSION_COOKIE_SECURE)
            self.assertFalse(configured.SIMPLE_JWT["AUTH_COOKIE_SECURE"])
            self.assertFalse(configured.CELERY_TASK_ALWAYS_EAGER)
            self.assertEqual(
                configured.DATABASES["default"]["ENGINE"],
                "django.db.backends.postgresql",
            )
            self.assertEqual(
                configured.CACHES["default"]["BACKEND"],
                "django.core.cache.backends.redis.RedisCache",
            )
            self.assertEqual(configured.CELERY_BROKER_URL, "redis://127.0.0.1:6379/2")

    def test_smtp_backend_receives_finite_timeout(self):
        with self.production_settings() as configured:
            with self.settings(MAILERS=configured.MAILERS):
                self.assertEqual(mail.mailers["default"].timeout, 10)

    @contextmanager
    def production_settings(self, **overrides):
        values = {
            "SECRET_KEY": "synthetic-production-test-key-with-at-least-thirty-two-bytes",
            "ALLOWED_HOSTS": "api.example.com",
            "CSRF_TRUSTED_ORIGINS": "https://api.example.com",
            "DATABASE_URL": "postgresql://postgres:test@127.0.0.1:5432/test",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            **overrides,
        }
        with patch("os.getenv", side_effect=values.get):
            yield importlib.reload(importlib.import_module("app.settings.prod"))

    def test_proxy_count_accepts_zero_and_positive(self):
        with self.production_settings() as configured:
            self.assertEqual(configured.NUM_PROXIES, 0)
        for count in ("0", "1", "3"):
            with (
                self.subTest(count=count),
                self.production_settings(NUM_PROXIES=count) as configured,
            ):
                self.assertEqual(configured.NUM_PROXIES, int(count))

    def test_proxy_count_rejects_negative_and_malformed_values(self):
        for count in ("-1", "abc", "1.5", "", " "):
            with self.subTest(count=count):
                with self.assertRaisesMessage(
                    ImproperlyConfigured, "NUM_PROXIES must be a nonnegative integer."
                ):
                    with self.production_settings(NUM_PROXIES=count):
                        pass
