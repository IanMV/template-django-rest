import logging
import secrets

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from core.auth.rate_limit import limit_code_requests
from core.auth.services import SessionService
from core.models import PasswordReset, User
from core.shared.email_token_sender import send_email_token
from core.shared.response_messages import MSG_CODE_INVALID

logger = logging.getLogger(__name__)


class PasswordResetService:
    @staticmethod
    def request_reset(email, ip_address=None):
        email = User.objects.normalize_email(email)
        limit_code_requests("password-reset", email, ip_address)
        reset_code = None
        try:
            with transaction.atomic():
                user = User.objects.select_for_update(no_key=True).filter(
                    email=email, is_active=True
                ).first()
                if user is None:
                    return
                raw_code = f"{secrets.randbelow(1000000):06d}"
                PasswordReset.objects.filter(user=user).delete()
                reset_code = PasswordReset(user=user)
                reset_code.set_code(raw_code)
                reset_code.save()
            send_email_token(
                email, raw_code, "password_reset", expires_at=reset_code.expires_at
            )
        except Exception as exc:
            logger.error("Password reset code issuance failed (%s)", type(exc).__name__)
            if reset_code is not None:
                try:
                    PasswordReset.objects.filter(pk=reset_code.pk).delete()
                except Exception as cleanup_error:
                    logger.error(
                        "Password reset code cleanup failed (%s)",
                        type(cleanup_error).__name__,
                    )

    @staticmethod
    def confirm_reset(email, code, new_password):
        email = User.objects.normalize_email(email)
        with transaction.atomic():
            user = User.objects.select_for_update(no_key=True).filter(
                email=email, is_active=True
            ).first()
            reset_code = (
                PasswordReset.objects.select_for_update().filter(user=user).first()
            )
            valid = reset_code is not None and reset_code.verify(code)
            if valid:
                try:
                    validate_password(new_password, user=user)
                except DjangoValidationError as exc:
                    raise serializers.ValidationError(
                        {"new_password": list(exc.messages)}
                    ) from exc
                user.set_password(new_password)
                user.save(update_fields=["password", "updated_at"])
                reset_code.mark_used()
                SessionService.revoke_all_sessions(user)
        if not valid:
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
        return user
