import logging
import secrets

from django.db import transaction
from rest_framework import serializers

from core.auth.rate_limit import limit_code_requests
from core.models.email_verification import EmailVerification
from core.models.user import User
from core.shared.email_token_sender import queue_email, send_email_token
from core.shared.exceptions import ServiceUnavailable
from core.shared.response_messages import MSG_CODE_INVALID

logger = logging.getLogger(__name__)


class RegistrationService:
    @staticmethod
    def request_registration(email: str, ip_address: str | None = None) -> None:
        email = User.objects.normalize_email(email)
        limit_code_requests("registration", email, ip_address)
        try:
            with transaction.atomic():
                user, created = User.objects.get_or_create(
                    email=email, defaults={"is_active": False}
                )
                user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
                if not created and user.is_active:
                    def notify():
                        try:
                            queue_email(
                                user.email,
                                "Registration attempt on existing account",
                                "Registration attempt on existing account. "
                                "If this was you, please log in or reset your password.",
                            )
                        except Exception as exc:
                            logger.error("Registration security notice enqueue failed (%s)", type(exc).__name__)

                    transaction.on_commit(notify)
                    return
                if user.password or user.is_staff or user.is_superuser:
                    return
                raw_code = f"{secrets.randbelow(1000000):06d}"
                EmailVerification.objects.filter(user=user).delete()
                verification = EmailVerification(user=user)
                verification.set_code(raw_code)
                verification.save()
                def send():
                    try:
                        send_email_token(user.email, raw_code, "verification_code", expires_at=verification.expires_at)
                    except Exception:
                        EmailVerification.objects.filter(pk=verification.pk).delete()
                        if created:
                            User.objects.filter(
                                pk=user.pk,
                                is_active=False,
                                emailverification__isnull=True,
                            ).delete()
                        raise ServiceUnavailable() from None

                transaction.on_commit(send)
        except Exception as exc:
            logger.error("Registration code issuance failed (%s)", type(exc).__name__)
            raise ServiceUnavailable() from exc

    @staticmethod
    def verify_code(email: str, code: str) -> bool:
        email = User.objects.normalize_email(email)
        with transaction.atomic():
            user = User.objects.select_for_update(no_key=True).filter(
                email=email, is_active=False, password="", is_staff=False, is_superuser=False
            ).first()
            verification = (
                EmailVerification.objects.select_for_update()
                .filter(user=user)
                .first()
            )
            valid = verification is not None and verification.verify(code)
        if not valid:
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
        return True

    @staticmethod
    def confirm_registration(email: str, code: str, name: str, password: str) -> None:
        email = User.objects.normalize_email(email)
        with transaction.atomic():
            user = User.objects.select_for_update(no_key=True).filter(
                email=email, is_active=False, password="", is_staff=False, is_superuser=False
            ).first()
            verification = (
                EmailVerification.objects.select_for_update()
                .filter(user=user)
                .first()
            )
            valid = verification is not None and verification.verify(code)
            if valid:
                user.name = name
                user.set_password(password)
                user.is_active = True
                user.save(update_fields=["name", "password", "is_active", "updated_at"])
                verification.mark_used()
        if not valid:
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
