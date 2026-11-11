from pathlib import Path
from runpy import run_path
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class DevelopmentMailSettingsTests(SimpleTestCase):
    def test_empty_or_whitespace_sender_uses_development_fallback(self):
        for value in ("", "   ", " sender@example.com "):
            with self.subTest(value=value):
                self.assertEqual(
                    self.configured(DEFAULT_FROM_EMAIL=value)["DEFAULT_FROM_EMAIL"],
                    value.strip() or "noreply@localhost",
                )

    def configured(self, **values):
        with patch(
            "os.getenv", side_effect=lambda key, default=None: values.get(key, default)
        ):
            return run_path(
                str(Path(__file__).resolve().parent.parent / "app/settings/dev.py"),
                run_name="app.settings._dev_settings_test",
            )

    def test_console_default_has_no_smtp_options(self):
        configured = self.configured(EMAIL_PORT="not-a-port", EMAIL_USE_SSL="true")
        self.assertEqual(
            configured["MAILERS"],
            {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}},
        )
        self.assertEqual(configured["DEFAULT_FROM_EMAIL"], "noreply@localhost")

    def test_smtp_options_have_correct_types_and_timeout(self):
        configured = self.configured(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
            EMAIL_HOST="smtp.example.com",
            EMAIL_PORT="465",
            EMAIL_HOST_USER="test-user",
            EMAIL_HOST_PASSWORD="synthetic-test-password",
            EMAIL_USE_TLS="False",
            EMAIL_USE_SSL="True",
            DEFAULT_FROM_EMAIL="test@example.com",
        )
        with self.settings(MAILERS=configured["MAILERS"]):
            backend = mail.mailers["default"]
            self.assertEqual(backend.host, "smtp.example.com")
            self.assertEqual(backend.port, 465)
            self.assertIs(backend.use_tls, False)
            self.assertIs(backend.use_ssl, True)
            self.assertEqual(backend.username, "test-user")
            self.assertEqual(backend.password, "synthetic-test-password")
            self.assertEqual(backend.timeout, 10)
        self.assertEqual(configured["DEFAULT_FROM_EMAIL"], "test@example.com")

    def test_smtp_defaults_to_starttls_on_port_587(self):
        configured = self.configured(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
            EMAIL_HOST="smtp.example.com",
        )
        options = configured["MAILERS"]["default"]["OPTIONS"]
        self.assertEqual(options["port"], 587)
        self.assertIs(options["use_tls"], True)
        self.assertIs(options["use_ssl"], False)

    def test_smtp_requires_host(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "EMAIL_HOST"):
            self.configured(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")

    def test_tls_and_ssl_cannot_be_enabled_together(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "not both"):
            self.configured(
                EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                EMAIL_HOST="smtp.example.com",
                EMAIL_USE_TLS="true",
                EMAIL_USE_SSL="true",
            )
        with self.assertRaisesMessage(ImproperlyConfigured, "not both"):
            self.configured(
                EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                EMAIL_HOST="smtp.example.com",
                EMAIL_USE_TLS=" true ",
                EMAIL_USE_SSL=" TRUE ",
            )

    def test_smtp_boolean_settings_strip_spaces_and_reject_invalid_values(self):
        configured = self.configured(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
            EMAIL_HOST="smtp.example.com",
            EMAIL_USE_TLS=" true ",
            EMAIL_USE_SSL=" false ",
        )
        options = configured["MAILERS"]["default"]["OPTIONS"]
        self.assertIs(options["use_tls"], True)
        self.assertIs(options["use_ssl"], False)

        for key in ("EMAIL_USE_TLS", "EMAIL_USE_SSL"):
            for value in ("yes", "no", "1", "0", "", "   ", "invalid"):
                with (
                    self.subTest(key=key, value=value),
                    self.assertRaisesMessage(ImproperlyConfigured, key),
                ):
                    self.configured(
                        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                        EMAIL_HOST="smtp.example.com",
                        **{key: value},
                    )
