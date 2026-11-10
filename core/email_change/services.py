import logging
import secrets

from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from core.auth.rate_limit import limit_code_requests, require_current_password
from core.auth.services import SessionService, require_unchanged_user
from core.models import EmailChange, PasswordReset, User
from core.shared.email_token_sender import send_email_token
from core.shared.exceptions import ServiceUnavailable
from core.shared.response_messages import MSG_CODE_INVALID, MSG_EMAIL_IN_USE

logger = logging.getLogger(__name__)


class EmailChangeService:
    @staticmethod
    def request_change(user, new_email, current_password, ip_address=None):
        new_email = User.objects.normalize_email(new_email)
        require_current_password(user, current_password)
        limit_code_requests("email-change", new_email, ip_address)
        if User.objects.filter(email=new_email).exists():
            raise serializers.ValidationError({"new_email": MSG_EMAIL_IN_USE})
        change_code = None
        try:
            with transaction.atomic():
                current = (
                    User.objects.select_for_update(no_key=True)
                    .filter(pk=user.pk)
                    .first()
                )
                require_unchanged_user(user, current)
                raw_code = f"{secrets.randbelow(1000000):06d}"
                EmailChange.objects.filter(user=current).delete()
                change_code = EmailChange(user=current, new_email=new_email)
                change_code.set_code(raw_code)
                change_code.save()
            send_email_token(
                new_email, raw_code, "email_change", expires_at=change_code.expires_at
            )
        except AuthenticationFailed:
            raise
        except Exception as exc:
            logger.error("Email change code issuance failed (%s)", type(exc).__name__)
            if change_code is not None:
                try:
                    EmailChange.objects.filter(pk=change_code.pk).delete()
                except Exception as cleanup_error:
                    logger.error(
                        "Email change code cleanup failed (%s)",
                        type(cleanup_error).__name__,
                    )
            raise ServiceUnavailable() from None

    @staticmethod
    def confirm_change(user, code, current_password):
        require_current_password(user, current_password)
        with transaction.atomic():
            current = (
                User.objects.select_for_update(no_key=True).filter(pk=user.pk).first()
            )
            require_unchanged_user(user, current)
            change_code = (
                EmailChange.objects.select_for_update().filter(user=current).first()
            )
            valid = change_code is not None and change_code.verify(code)
            if valid:
                new_email = User.objects.normalize_email(change_code.new_email)
                if User.objects.filter(email=new_email).exclude(pk=current.pk).exists():
                    raise serializers.ValidationError({"new_email": MSG_EMAIL_IN_USE})
                try:
                    with transaction.atomic():
                        current.email = new_email
                        current.save(update_fields=["email", "updated_at"])
                except IntegrityError:
                    raise serializers.ValidationError(
                        {"new_email": MSG_EMAIL_IN_USE}
                    ) from None
                change_code.mark_used()
                PasswordReset.objects.filter(user=current).delete()
                SessionService.revoke_all_sessions(current)
        if not valid:
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
