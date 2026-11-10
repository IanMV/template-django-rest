from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.utils import timezone

from core.shared.email_token_sender import send_email, send_email_token
from tests.base import ApiCase


class EmailSenderTests(ApiCase):
    def test_expired_code_is_not_sent(self):
        with self.assertRaisesMessage(ValueError, "expired"):
            send_email_token(
                "test@example.com",
                "123456",
                "password_reset",
                expires_at=timezone.now(),
            )
        self.assertFalse(mail.outbox)

    def test_smtp_failure_propagates_to_issuance_cleanup(self):
        with patch(
            "core.shared.email_token_sender.EmailMultiAlternatives.send",
            side_effect=TimeoutError("offline"),
        ):
            with self.assertRaises(TimeoutError):
                send_email_token(
                    "test@example.com",
                    "123456",
                    "password_reset",
                    expires_at=timezone.now() + timedelta(minutes=15),
                )

    def test_silent_backend_failure_is_not_reported_as_sent(self):
        with patch(
            "core.shared.email_token_sender.EmailMultiAlternatives.send", return_value=0
        ):
            with self.assertRaisesMessage(RuntimeError, "not sent"):
                send_email("test@example.com", "Subject", "Body")
