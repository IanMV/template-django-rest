import secrets

from django.db import transaction
from rest_framework import serializers

from core.exceptions import ServiceUnavailable
from core.models.email_change import EmailChange
from core.models.user import User
from core.services.rate_limit import limit_code_requests
from core.services.user import SessionService
from core.utils.email_token_sender import send_email_token


class EmailChangeService:
    @staticmethod
    def request_change(
        user: User, new_email: str, ip_address: str | None = None
    ) -> None:
        limit_code_requests("email-change", new_email, ip_address)
        if User.objects.filter(email=new_email).exists():
            raise serializers.ValidationError(
                {"new_email": "This e-mail is already in use."}
            )

        raw_code = f"{secrets.randbelow(1000000):06d}"
        try:
            with transaction.atomic():
                EmailChange.objects.filter(user=user).delete()
                change_code = EmailChange(user=user, new_email=new_email)
                change_code.set_code(raw_code)
                change_code.save()
                send_email_token(new_email, raw_code, "Confirm your new e-mail address")
        except Exception as exc:
            raise ServiceUnavailable() from exc

    @staticmethod
    def verify_code(user: User, code: str) -> bool:
        change_code = EmailChange.objects.filter(user=user).first()
        if not change_code or not change_code.verify(code):
            raise serializers.ValidationError(
                {"code": "Invalid or expired verification code."}
            )
        return True

    @staticmethod
    def confirm_change(user: User, code: str, current_password: str) -> None:
        if not user.check_password(current_password):
            raise serializers.ValidationError({"password": "Invalid current password."})

        with transaction.atomic():
            change_code = EmailChange.objects.select_for_update().filter(user=user).first()
            valid = change_code is not None and change_code.verify(code)
            if valid:
                if User.objects.filter(email=change_code.new_email).exclude(pk=user.pk).exists():
                    raise serializers.ValidationError(
                        {"new_email": "This e-mail is already in use."}
                    )
                user.email = change_code.new_email
                user.save(update_fields=["email", "updated_at"])
                change_code.mark_used()
                SessionService.revoke_all_sessions(user)
        if not valid:
            raise serializers.ValidationError(
                {"code": "Invalid or expired verification code."}
            )
