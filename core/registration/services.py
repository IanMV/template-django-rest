import logging
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from core.auth.rate_limit import limit_code_requests
from core.models import EmailVerification, User
from core.shared.email_token_sender import send_email, send_email_token
from core.shared.exceptions import ServiceUnavailable
from core.shared.response_messages import MSG_CODE_INVALID

logger = logging.getLogger(__name__)


class RegistrationService:
    @staticmethod
    def request_registration(email, ip_address=None):
        email = User.objects.normalize_email(email)
        limit_code_requests("registration", email, ip_address)
        verification = None
        try:
            with transaction.atomic():
                user, _ = User.objects.select_for_update(no_key=True).get_or_create(
                    email=email, defaults={"is_active": False}
                )
                if not user.is_active:
                    if user.password or user.is_staff or user.is_superuser:
                        return
                    if EmailVerification.objects.filter(
                        user=user,
                        created_at__gt=timezone.now() - timedelta(seconds=60),
                    ).exists():
                        return
                    raw_code = f"{secrets.randbelow(1000000):06d}"
                    EmailVerification.objects.filter(user=user).delete()
                    verification = EmailVerification(user=user)
                    verification.set_code(raw_code)
                    verification.save()

            if verification is None:
                send_email(
                    email,
                    "Registration attempt on existing account",
                    "If this was you, please log in or reset your password.",
                )
            else:
                send_email_token(
                    email,
                    raw_code,
                    "verification_code",
                    expires_at=verification.expires_at,
                )
        except Exception as exc:
            logger.error("Registration code issuance failed (%s)", type(exc).__name__)
            # Do not delete the user: a concurrent confirmation may already have activated it.
            if verification is not None:
                try:
                    EmailVerification.objects.filter(pk=verification.pk).delete()
                except Exception as cleanup_error:
                    logger.error(
                        "Registration code cleanup failed (%s)",
                        type(cleanup_error).__name__,
                    )
            raise ServiceUnavailable() from None

    @staticmethod
    def confirm_registration(email, code, name, password):
        email = User.objects.normalize_email(email)
        with transaction.atomic():
            user = (
                User.objects.select_for_update(no_key=True)
                .filter(
                    email=email,
                    is_active=False,
                    password="",
                    is_staff=False,
                    is_superuser=False,
                )
                .first()
            )
            verification = (
                EmailVerification.objects.select_for_update().filter(user=user).first()
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
