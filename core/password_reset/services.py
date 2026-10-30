import secrets

from django.db import transaction
from rest_framework import serializers

from core.shared.exceptions import ServiceUnavailable
from core.models.password_reset import PasswordReset
from core.models.user import User
from core.shared.response_messages import MSG_CODE_INVALID
from core.auth.rate_limit import limit_code_requests
from core.auth.services import SessionService
from core.shared.email_token_sender import send_email_token


class PasswordResetService:
    @staticmethod
    def request_reset(email: str, ip_address: str | None = None) -> None:
        limit_code_requests("password-reset", email, ip_address)
        user = User.objects.filter(email=email, is_active=True).first()
        if not user:
            return

        raw_code = f"{secrets.randbelow(1000000):06d}"

        try:
            with transaction.atomic():
                PasswordReset.objects.filter(user=user).delete()
                reset_code = PasswordReset(user=user)
                reset_code.set_code(raw_code)
                reset_code.save()
                send_email_token(user.email, raw_code, "Your password reset code")
        except Exception as exc:
            raise ServiceUnavailable() from exc

    @staticmethod
    def verify_code(email: str, code: str) -> bool:
        user = User.objects.filter(email=email, is_active=True).first()
        reset_code = PasswordReset.objects.filter(user=user).first() if user else None

        if not reset_code or not reset_code.verify(code):
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})

        return True

    @staticmethod
    def confirm_reset(email: str, code: str, new_password: str) -> None:
        with transaction.atomic():
            reset_code = PasswordReset.objects.select_for_update().filter(
                user__email=email, user__is_active=True
            ).first()
            valid = reset_code is not None and reset_code.verify(code)
            if valid:
                user = reset_code.user
                user.set_password(new_password)
                user.save(update_fields=["password", "updated_at"])
                reset_code.mark_used()
                SessionService.revoke_all_sessions(user)
        if not valid:
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
