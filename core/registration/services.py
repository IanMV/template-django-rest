import logging
import secrets

from django.core.mail import EmailMessage
from django.db import transaction
from rest_framework import serializers

from core.auth.rate_limit import limit_code_requests
from core.models.email_verification import EmailVerification
from core.models.user import User
from core.shared.email_token_sender import send_email_token
from core.shared.exceptions import ServiceUnavailable
from core.shared.response_messages import MSG_CODE_INVALID

logger = logging.getLogger(__name__)


class RegistrationService:
    @staticmethod
    def request_registration(email: str, ip_address: str | None = None) -> None:
        limit_code_requests("registration", email, ip_address)
        try:
            with transaction.atomic():
                user, created = User.objects.get_or_create(
                    email=email, defaults={"is_active": False}
                )
                if not created and user.is_active:
                    def notify():
                        try:
                            EmailMessage(
                                subject="Registration attempt on existing account",
                                body=(
                                    "Registration attempt on existing account. "
                                    "If this was you, please log in or reset your password."
                                ),
                                to=[user.email],
                            ).send()
                        except Exception:
                            logger.exception("Registration security notice delivery failed")

                    transaction.on_commit(notify)
                    return
                raw_code = f"{secrets.randbelow(1000000):06d}"
                EmailVerification.objects.filter(user=user).delete()
                verification = EmailVerification(user=user)
                verification.set_code(raw_code)
                verification.save()
                def send():
                    try:
                        send_email_token(user.email, raw_code, "Verify your e-mail")
                    except Exception as exc:
                        EmailVerification.objects.filter(pk=verification.pk).delete()
                        if created:
                            User.objects.filter(
                                pk=user.pk,
                                is_active=False,
                                emailverification__isnull=True,
                            ).delete()
                        raise ServiceUnavailable() from exc

                transaction.on_commit(send)
        except Exception as exc:
            logger.exception("Registration code issuance failed")
            raise ServiceUnavailable() from exc

    @staticmethod
    def verify_code(email: str, code: str) -> bool:
        with transaction.atomic():
            verification = (
                EmailVerification.objects.select_for_update()
                .filter(user__email=email, user__is_active=False)
                .first()
            )
            valid = verification is not None and verification.verify(code)
        if not valid:
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
        return True

    @staticmethod
    def confirm_registration(email: str, code: str, name: str, password: str) -> None:
        with transaction.atomic():
            verification = (
                EmailVerification.objects.select_for_update()
                .filter(user__email=email, user__is_active=False)
                .first()
            )
            valid = verification is not None and verification.verify(code)
            if valid:
                user = verification.user
                user.name = name
                user.set_password(password)
                user.is_active = True
                user.save(update_fields=["name", "password", "is_active", "updated_at"])
                verification.mark_used()
        if not valid:
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
