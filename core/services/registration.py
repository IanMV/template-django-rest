import secrets

from django.db import transaction
from rest_framework import serializers

from core.shared.exceptions import ServiceUnavailable
from core.models.email_verification import EmailVerification
from core.models.user import User
from core.shared.response_messages import (
    MSG_CODE_INVALID,
    MSG_EMAIL_ALREADY_EXIST,
)
from core.auth.rate_limit import limit_code_requests
from core.shared.email_token_sender import send_email_token


class RegistrationService:
    @staticmethod
    def request_registration(email: str, ip_address: str | None = None) -> None:
        limit_code_requests("registration", email, ip_address)
        raw_code = f"{secrets.randbelow(1000000):06d}"
        try:
            with transaction.atomic():
                user, created = User.objects.get_or_create(
                    email=email, defaults={"is_active": False}
                )
                if not created and user.is_active:
                    raise serializers.ValidationError({"email": MSG_EMAIL_ALREADY_EXIST})
                EmailVerification.objects.filter(user=user).delete()
                verification = EmailVerification(user=user)
                verification.set_code(raw_code)
                verification.save()
                send_email_token(user.email, raw_code, "Verify your e-mail")
        except serializers.ValidationError:
            raise
        except Exception as exc:
            raise ServiceUnavailable() from exc

    @staticmethod
    def verify_code(email: str, code: str) -> bool:
        user = User.objects.filter(email=email).first()
        verification = (
            EmailVerification.objects.filter(user=user).first() if user else None
        )

        if not verification or not verification.verify(code):
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
        return True

    @staticmethod
    def confirm_registration(email: str, code: str, name: str, password: str) -> None:
        with transaction.atomic():
            verification = EmailVerification.objects.select_for_update().filter(
                user__email=email, user__is_active=False
            ).first()
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
