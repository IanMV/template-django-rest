import logging
import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from core.auth.rate_limit import limit_code_requests, require_current_password
from core.auth.services import SessionService, require_unchanged_user
from core.models import EmailChange, PasswordReset, User
from core.shared.email_token_sender import send_email_token
from core.shared.response_messages import MSG_CODE_INVALID, MSG_EMAIL_IN_USE

logger = logging.getLogger(__name__)


class EmailChangeService:
    @staticmethod
    def request_change(user, new_email, current_password, ip_address=None):
        new_email = User.objects.normalize_email(new_email)
        require_current_password(user, current_password)
        limit_code_requests("email-change", new_email, ip_address)
        change_code = None
        try:
            with transaction.atomic():
                current = (
                    User.objects.select_for_update(no_key=True)
                    .filter(pk=user.pk)
                    .first()
                )
                require_unchanged_user(user, current)
                occupant = User.objects.filter(email=new_email).first()
                if occupant is not None and not occupant.is_provisional_registration:
                    return
                if EmailChange.objects.filter(
                    user=current,
                    new_email=new_email,
                    created_at__gt=timezone.now() - timedelta(seconds=60),
                ).exists():
                    return
                raw_code = f"{secrets.randbelow(1000000):06d}"
                EmailChange.objects.filter(user=current).delete()
                change_code = EmailChange(user=current, new_email=new_email)
                change_code.set_code(raw_code)
                change_code.save()
            send_email_token(
                new_email, raw_code, "email_change", expires_at=change_code.expires_at
            )
        except AuthenticationFailed, serializers.ValidationError:
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
            # Issuance errors must not distinguish an available address from an occupied one.

    @staticmethod
    def confirm_change(user, code, current_password):
        require_current_password(user, current_password)
        with transaction.atomic():
            snapshot = EmailChange.objects.filter(user=user).first()
            destination = snapshot.new_email if snapshot is not None else None
            locked_users = list(
                User.objects.select_for_update(no_key=True)
                .filter(Q(pk=user.pk) | Q(email=destination))
                .order_by("pk")
            )
            current = next((item for item in locked_users if item.pk == user.pk), None)
            require_unchanged_user(user, current)
            change_code = (
                EmailChange.objects.select_for_update()
                .filter(user=current, pk=snapshot.pk if snapshot is not None else None)
                .first()
            )
            valid = change_code is not None and change_code.verify(code)
            if valid:
                new_email = User.objects.normalize_email(change_code.new_email)
                occupant = next(
                    (item for item in locked_users if item.email == new_email), None
                )
                if occupant is not None and occupant.pk != current.pk:
                    if not occupant.is_provisional_registration:
                        raise serializers.ValidationError(
                            {"new_email": MSG_EMAIL_IN_USE}
                        )
                    occupant.delete()
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
