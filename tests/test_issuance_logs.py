from contextlib import ExitStack
from unittest.mock import patch

from django.db import IntegrityError
from django.db.models.query import QuerySet

from core.models import EmailChange, EmailVerification, PasswordReset
from core.shared.tasks import send_async_email
from tests.base import ApiTransactionCase


class IssuanceLogSafetyTests(ApiTransactionCase):
    def test_database_queue_and_cleanup_errors_do_not_log_secrets(self):
        markers = (
            "private@example.invalid",
            "OTP_479213",
            "PASSWORD_marker",
            "JWT_marker",
        )
        message = " ".join(markers)
        flows = (
            ("registration", EmailVerification, 503),
            ("password-reset", PasswordReset, 200),
            ("email-change", EmailChange, 503),
        )
        for kind in ("database", "queue", "cleanup"):
            for index, (flow, model, status) in enumerate(flows):
                with self.subTest(kind=kind, flow=flow):
                    user = self.create_user(email=f"{kind}-{flow}@example.com")
                    recipient = f"new-{kind}-{flow}@example.com"
                    data = {"email": recipient}
                    if flow == "password-reset":
                        recipient = user.email
                        data = {"email": recipient}
                    elif flow == "email-change":
                        self.login(user)
                        data = {"new_email": recipient, "password": self.password}
                    module = {
                        "registration": "core.registration.services",
                        "password-reset": "core.password_reset.services",
                        "email-change": "core.email_change.services",
                    }[flow]
                    enqueue_failed = False
                    delete = QuerySet.delete

                    def fail_enqueue(*args, **kwargs):
                        nonlocal enqueue_failed
                        enqueue_failed = True
                        raise OSError(message)

                    def fail_cleanup(queryset):
                        if enqueue_failed and queryset.model is model:
                            raise IntegrityError(message)
                        return delete(queryset)

                    with ExitStack() as stack:
                        if kind == "database":
                            stack.enter_context(
                                patch.object(
                                    model.objects,
                                    "filter",
                                    side_effect=IntegrityError(message),
                                )
                            )
                        else:
                            stack.enter_context(
                                patch.object(
                                    send_async_email,
                                    "apply_async",
                                    side_effect=fail_enqueue,
                                )
                            )
                            if kind == "cleanup":
                                stack.enter_context(
                                    patch.object(QuerySet, "delete", fail_cleanup)
                                )
                        logs = stack.enter_context(
                            self.assertLogs(module, level="ERROR")
                        )
                        response = self.client.post(
                            f"/api/{flow}/request/",
                            data,
                            format="json",
                            REMOTE_ADDR=f"127.0.0.{1 + index + 3 * ('database', 'queue', 'cleanup').index(kind)}",
                        )
                    self.assertEqual(response.status_code, status)
                    recorded = " ".join(logs.output)
                    for marker in markers:
                        self.assertNotIn(marker, recorded)
                    self.assertIn("failed", recorded.lower())
                    if kind in ("database", "queue"):
                        lookup = (
                            {"user__email": recipient}
                            if flow == "registration"
                            else {"user": user}
                        )
                        self.assertFalse(model.objects.filter(**lookup).exists())
                    if kind == "cleanup":
                        self.assertIn("IntegrityError", recorded)
