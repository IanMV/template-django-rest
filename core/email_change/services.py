import logging
import secrets

from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from core.auth.rate_limit import limit_code_requests, require_current_password
from core.auth.services import SessionService, require_unchanged_user
from core.models import PasswordReset
from core.models.email_change import EmailChange
from core.models.user import User
from core.shared.email_token_sender import send_email_token
from core.shared.exceptions import ServiceUnavailable
from core.shared.response_messages import (
    MSG_CODE_INVALID,
    MSG_EMAIL_IN_USE,
)

logger = logging.getLogger(__name__)


class EmailChangeService:
    @staticmethod
    def request_change(
        user: User, new_email: str, current_password: str, ip_address: str | None = None, request=None
    ) -> None:
        new_email = User.objects.normalize_email(new_email)
        require_current_password(user, current_password, request=request, action="email_change_request")
        limit_code_requests("email-change", new_email, ip_address)
        if User.objects.filter(email=new_email).exists():
            raise serializers.ValidationError(
                {"new_email": MSG_EMAIL_IN_USE}
            )

        raw_code = f"{secrets.randbelow(1000000):06d}"
        try:
            with transaction.atomic():
                current = User.objects.select_for_update(no_key=True).filter(pk=user.pk).first()
                require_unchanged_user(user, current)
                user = current
                EmailChange.objects.filter(user=user).delete()
                change_code = EmailChange(user=user, new_email=new_email)
                change_code.set_code(raw_code)
                change_code.save()
                def send():
                    try:
                        send_email_token(new_email, raw_code, "email_change", expires_at=change_code.expires_at)
                    except Exception:
                        EmailChange.objects.filter(pk=change_code.pk).delete()
                        raise ServiceUnavailable() from None

                transaction.on_commit(send)
        except AuthenticationFailed:
            raise
        except Exception as exc:
            logger.error("Email change code issuance failed (%s)", type(exc).__name__)
            raise ServiceUnavailable() from exc

    @staticmethod
    def verify_code(user: User, code: str) -> bool:
        with transaction.atomic():
            current = User.objects.select_for_update(no_key=True).filter(pk=user.pk).first()
            require_unchanged_user(user, current)
            change_code = (
                EmailChange.objects.select_for_update().filter(user=user).first()
            )
            valid = change_code is not None and change_code.verify(code)
        if not valid:
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
        return True

    @staticmethod
    def confirm_change(user: User, code: str, current_password: str, request=None) -> None:
        require_current_password(user, current_password, request=request, action="email_change_confirm")

        with transaction.atomic():
            current = User.objects.select_for_update(no_key=True).filter(pk=user.pk).first()
            require_unchanged_user(user, current)
            user = current
            change_code = (
                EmailChange.objects.select_for_update().filter(user=user).first()
            )
            valid = change_code is not None and change_code.verify(code)
            if valid:
                change_code.new_email = User.objects.normalize_email(change_code.new_email)
                if (
                    User.objects.filter(email=change_code.new_email)
                    .exclude(pk=user.pk)
                    .exists()
                ):
                    raise serializers.ValidationError(
                        {"new_email": MSG_EMAIL_IN_USE}
                    )
                try:
                    user.email = change_code.new_email
                    user.save(update_fields=["email", "updated_at"])
                except IntegrityError:
                    raise serializers.ValidationError(
                        {"new_email": MSG_EMAIL_IN_USE}
                    )
                change_code.mark_used()
                PasswordReset.objects.filter(user=user).delete()
                SessionService.revoke_all_sessions(user)
        if not valid:
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
