from smtplib import SMTPException
from unittest.mock import patch

from celery.exceptions import Retry
from django.core import mail

from core.models import EmailChange, EmailVerification, PasswordReset
from core.shared.tasks import send_async_email
from tests.base import ApiCase, ApiTransactionCase


class AsyncEmailTests(ApiCase):
    def test_smtp_timeout_retries_without_leaking_recipient_or_code(self):
        recipient, code = "private@example.com", "123456"
        with patch(
            "core.shared.tasks.EmailMultiAlternatives.send",
            side_effect=TimeoutError(f"{recipient} {code}"),
        ):
            with patch.object(
                send_async_email, "retry", side_effect=Retry("masked")
            ) as retry:
                with self.assertRaises(Retry):
                    send_async_email.apply(
                        args=(recipient, "Test", code, None), throw=True
                    )
            self.assertEqual(retry.call_args.kwargs["max_retries"], 3)
            self.assertEqual(retry.call_args.kwargs["countdown"], 1)
            self.assertNotIn(recipient, str(retry.call_args.kwargs["exc"]))
            self.assertNotIn(code, str(retry.call_args.kwargs["exc"]))
            with self.assertLogs("core.shared.tasks", level="ERROR") as logs:
                with self.assertRaisesMessage(RuntimeError, "Email delivery failed"):
                    send_async_email.apply(
                        args=(recipient, "Test", code, None), retries=3, throw=True
                    )
            self.assertNotIn(recipient, " ".join(logs.output))
            self.assertNotIn(code, " ".join(logs.output))

    def test_queue_uses_rendered_bodies_expiry_and_redacted_arguments(self):
        with patch.object(
            send_async_email, "apply_async", wraps=send_async_email.apply_async
        ) as enqueue:
            response = self.post_with_commit(
                "/api/registration/request/", {"email": "new@example.com"}
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        options = enqueue.call_args.kwargs
        self.assertIn(self.email_code(), options["args"][2])
        self.assertIn(self.email_code(), options["args"][3])
        self.assertNotIn(self.email_code(), options["args"][1])
        self.assertEqual(
            options["expires"],
            EmailVerification.objects.get(user__email="new@example.com").expires_at,
        )
        self.assertNotIn(self.email_code(), options["argsrepr"])
        self.assertNotIn("new@example.com", options["argsrepr"])
        self.assertNotIn(self.email_code(), options["kwargsrepr"])

    def test_retries_only_mail_and_network_errors_without_leaking_code(self):
        secret = "123456"
        with patch(
            "core.shared.tasks.EmailMultiAlternatives.send",
            side_effect=SMTPException(secret),
        ) as send:
            with patch.object(
                send_async_email, "retry", side_effect=Retry("masked")
            ) as retry:
                with self.assertRaises(Retry):
                    send_async_email.apply(
                        args=("new@example.com", "Test", secret, None), throw=True
                    )
        self.assertEqual(send.call_count, 1)
        self.assertEqual(retry.call_args.kwargs["max_retries"], 3)
        self.assertEqual(retry.call_args.kwargs["countdown"], 1)
        self.assertNotIn(secret, str(retry.call_args.kwargs["exc"]))

        with patch(
            "core.shared.tasks.EmailMultiAlternatives.send",
            side_effect=SMTPException(secret),
        ):
            with self.assertLogs("core.shared.tasks", level="ERROR") as logs:
                with self.assertRaisesMessage(RuntimeError, "Email delivery failed"):
                    send_async_email.apply(
                        args=("new@example.com", "Test", secret, None),
                        retries=3,
                        throw=True,
                    )
        self.assertNotIn(secret, " ".join(logs.output))
        with patch(
            "core.shared.tasks.EmailMultiAlternatives.send",
            side_effect=ValueError("invalid"),
        ) as send:
            with self.assertLogs("core.shared.tasks", level="ERROR") as logs:
                with self.assertRaisesMessage(RuntimeError, "Email delivery failed"):
                    send_async_email.apply(
                        args=("new@example.com", "Test", secret, None), throw=True
                    )
        self.assertEqual(send.call_count, 1)
        self.assertNotIn(secret, " ".join(logs.output))

    def test_accepted_message_can_fail_later_without_changing_http_response(self):
        with patch.object(send_async_email, "apply_async", return_value=None):
            response = self.post_with_commit(
                "/api/registration/request/", {"email": "new@example.com"}
            )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            EmailVerification.objects.filter(user__email="new@example.com").exists()
        )
        with patch(
            "core.shared.tasks.EmailMultiAlternatives.send",
            side_effect=SMTPException("offline"),
        ):
            with self.assertLogs("core.shared.tasks", level="ERROR"):
                with self.assertRaisesMessage(RuntimeError, "Email delivery failed"):
                    send_async_email.apply(
                        args=("new@example.com", "Verify your e-mail", "code", None),
                        retries=3,
                        throw=True,
                    )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            EmailVerification.objects.filter(user__email="new@example.com").exists()
        )


class AsyncQueueFailureTests(ApiTransactionCase):
    def test_registration_queue_failure_invalidates_code_and_returns_503(self):
        with patch.object(
            send_async_email, "apply_async", side_effect=OSError("broker down")
        ):
            response = self.client.post(
                "/api/registration/request/",
                {"email": "new@example.com"},
                format="json",
            )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(EmailVerification.objects.exists())
        self.assertFalse(mail.outbox)

    def test_reset_queue_failure_is_indistinguishable_from_unknown_email(self):
        user = self.create_user()
        with patch.object(
            send_async_email, "apply_async", side_effect=OSError("broker down")
        ):
            response = self.client.post(
                "/api/password-reset/request/", {"email": user.email}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PasswordReset.objects.exists())
        self.assertFalse(mail.outbox)

    def test_email_change_queue_failure_invalidates_code_and_returns_503(self):
        user = self.create_user()
        self.login(user)
        with patch.object(
            send_async_email, "apply_async", side_effect=OSError("broker down")
        ):
            response = self.client.post(
                "/api/email-change/request/",
                {"new_email": "new@example.com", "password": self.password},
                format="json",
            )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(EmailChange.objects.exists())
        self.assertFalse(mail.outbox)
