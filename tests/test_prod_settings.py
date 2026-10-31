import importlib
from contextlib import contextmanager
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class ProductionSettingsTests(SimpleTestCase):
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
