import re
from contextlib import redirect_stdout
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.template.loader import render_to_string
from django.test import override_settings
from django.utils import timezone

from core.shared.email_templates import SUBJECTS, render_email_token
from core.shared.email_token_sender import send_email_token
from tests.base import ApiCase


class EmailTemplateTests(ApiCase):
    def assert_multipart(self, subject, recipient):
        message = mail.outbox[-1]
        self.assertEqual(message.subject, subject)
        self.assertEqual(message.to, [recipient])
        self.assertEqual(message.content_subtype, "plain")
        self.assertEqual(len(message.alternatives), 1)
        html, mime_type = message.alternatives[0]
        self.assertEqual(mime_type, "text/html")
        code = self.email_code()
        for body in (message.body, html):
            self.assertEqual(re.findall(r"(?<!\d)\d{6}(?!\d)", body), [code])
        self.assertNotIn(code, message.subject)
        self.assertNotIn("<script", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_rendering_subject_and_autoescape(self):
        for template_name, expected_subject in SUBJECTS.items():
            with self.subTest(template_name=template_name):
                subject, text, html = render_email_token(template_name, "123456")
                self.assertEqual(subject, expected_subject)
                self.assertNotIn("\n", subject)
                self.assertIn("123456", text)
                self.assertIn("123456", html)
                self.assertIn("<table", html)

        injected = "<script>alert(1)</script>"
        html = render_to_string("email/verification_code.html", {"code": injected})
        text = render_to_string("email/verification_code.txt", {"code": injected})
        self.assertNotIn(injected, html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn(injected, text)

    def test_sender_attaches_html_and_preserves_plain_text(self):
        send_email_token(
            "recipient@example.com",
            "123456",
            "password_reset",
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        self.assert_multipart(SUBJECTS["password_reset"], "recipient@example.com")

    @override_settings(
        MAILERS={
            "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}
        }
    )
    def test_console_sender_skips_templates_and_sends_plain_code(self):
        output = StringIO()
        with (
            patch("django.template.loader.render_to_string") as render,
            redirect_stdout(output),
        ):
            send_email_token(
                "recipient@example.com",
                "123456",
                "password_reset",
                expires_at=timezone.now() + timedelta(minutes=15),
            )
        render.assert_not_called()
        self.assertIn(SUBJECTS["password_reset"], output.getvalue())
        self.assertIn("Your code is: 123456", output.getvalue())
        self.assertNotIn("Content-Type: text/html", output.getvalue())

    def test_registration_issues_multipart_message(self):
        response = self.post_with_commit(
            "/api/registration/request/", {"email": "new@example.com"}
        )
        self.assertEqual(response.status_code, 201)
        self.assert_multipart(SUBJECTS["verification_code"], "new@example.com")

    def test_password_reset_issues_multipart_message(self):
        user = self.create_user()
        response = self.post_with_commit(
            "/api/password-reset/request/", {"email": user.email}
        )
        self.assertEqual(response.status_code, 200)
        self.assert_multipart(SUBJECTS["password_reset"], user.email)

    def test_email_change_issues_multipart_message(self):
        user = self.create_user()
        self.login(user)
        response = self.post_with_commit(
            "/api/email-change/request/",
            {"new_email": "new@example.com", "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        self.assert_multipart(SUBJECTS["email_change"], "new@example.com")
