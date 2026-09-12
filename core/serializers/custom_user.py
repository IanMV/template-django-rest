import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from core.models.email_change import EmailChange
from core.models.email_verification import EmailVerification
from core.models.password_reset import PasswordReset
from core.utils.email_token_sender import send_email_token

User = get_user_model()


CODE_VIA_EMAIL_SUCCESS = Response(
    {"detail": "If this e-mail exists, a code was sent."},
    status=status.HTTP_200_OK,
)

CODE_SENT = Response({"detail": "Code sent."}, status=status.HTTP_200_OK)

EMAIL_ALREADY_EXIST = Response(
    {"detail": "This e-mail is already in use."},
    status=status.HTTP_400_BAD_REQUEST,
)

PASSWORD_RESET_SUCCESS = Response(
    {"detail": "Password successfully reset."}, status=status.HTTP_200_OK
)

EMAIL_CHANGE_SUCCESS = Response(
    {"detail": "E-mail successfully changed."}, status=status.HTTP_200_OK
)

EMAIL_VERIFIED = Response(
    {"detail": "E-mail successful verified."}, status=status.HTTP_200_OK
)

INVALID_CODE = Response(
    {"detail": "Invalid or expired code."},
    status=status.HTTP_400_BAD_REQUEST,
)

VALID_CODE = Response(
    {"detail": "Valid code."},
    status=status.HTTP_200_OK,
)

CODE_DOESNT_EXIST = Response(
    {"detail": "No code request found for this user."},
    status=status.HTTP_400_BAD_REQUEST,
)

USER_CREATED_SUCCESSFULLY = Response(
    {"detail": "user successfully created."},
    status=status.HTTP_201_CREATED,
)


class ServiceUnavailable(APIException):
    status_code = 503
    default_detail = "Failed to send e-mail with code. Please try again later."
    default_code = "service_unavailable"


class BaseUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"


class UserListRetrieveSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ("id", "name", "email", "created_at")


class RegistrationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def save(self, **kwargs):
        email = self.validated_data["email"]
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={"is_active": False},
        )
        raw_code = f"{secrets.randbelow(1000000):06d}"
        try:
            verification, _ = EmailVerification.objects.update_or_create(user=user)
            verification.set_code(raw_code)
            verification.save()
            send_email_token(user.email, raw_code, "Verify your e-mail")
        except Exception:
            raise ServiceUnavailable()
        return CODE_SENT


class RegistrationConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, required=True)
    name = serializers.CharField(required=True, max_length=255)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    def validate_password(self, value):
        validate_password(value)
        return value

    def save(self, **kwargs):
        email = self.validated_data["email"]
        code = self.validated_data["code"]
        user = User.objects.filter(email=email).first()
        verification = (
            EmailVerification.objects.filter(user=user).first() if user else None
        )
        if not verification:
            return CODE_DOESNT_EXIST
        if not verification.verify(code):
            return INVALID_CODE
        user.name = self.validated_data["name"]
        user.set_password(self.validated_data["password"])
        user.is_active = True
        user.save(update_fields=["name", "password", "is_active", "updated_at"])
        verification.mark_used()
        return USER_CREATED_SUCCESSFULLY


class RegistrationVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, required=True)

    def save(self, **kwargs):
        email = self.validated_data["email"]
        code = self.validated_data["code"]
        user = User.objects.filter(email=email).first()
        verification = (
            EmailVerification.objects.filter(user=user).first() if user else None
        )
        if not verification:
            return CODE_DOESNT_EXIST
        if not verification.verify(code):
            return INVALID_CODE
        return VALID_CODE


from rest_framework import serializers


class UserPatchSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ("name",)

    def validate(self, attrs):
        forbidden_fields = {"email", "password"}
        received_fields = set(self.initial_data.keys())

        if forbidden_fields.intersection(received_fields):
            raise serializers.ValidationError(
                {"detail": "It is not possible to change these fields directly."}
            )

        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def save(self, **kwargs):
        email = self.validated_data["email"]
        user = User.objects.filter(email=email).first()
        if not user:
            return CODE_VIA_EMAIL_SUCCESS
        raw_code = f"{secrets.randbelow(1000000):06d}"
        try:
            PasswordReset.objects.filter(user=user).delete()
            reset_code = PasswordReset(user=user)
            reset_code.set_code(raw_code)
            reset_code.save()
            send_email_token(user.email, raw_code, "Your password reset code")
        except Exception:
            # transaction.set_rollback(True)
            raise ServiceUnavailable()
        return CODE_VIA_EMAIL_SUCCESS


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, required=True)
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def save(self, **kwargs):
        email = self.validated_data["email"]
        code = self.validated_data["code"]
        new_password = self.validated_data["new_password"]
        user = User.objects.filter(email=email).first()
        reset_code = PasswordReset.objects.filter(user=user).first() if user else None
        if not reset_code:
            return CODE_DOESNT_EXIST
        if not reset_code.verify(code):
            return INVALID_CODE
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        reset_code.mark_used()
        return PASSWORD_RESET_SUCCESS


class PasswordResetVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, required=True)

    def save(self, **kwargs):
        email = self.validated_data["email"]
        code = self.validated_data["code"]
        user = User.objects.filter(email=email).first()
        reset_code = PasswordReset.objects.filter(user=user).first() if user else None
        if not reset_code:
            return CODE_DOESNT_EXIST
        if not reset_code.verify(code):
            return INVALID_CODE
        return VALID_CODE


class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField(required=True)

    def save(self, **kwargs):
        new_email = self.validated_data["new_email"]
        user = kwargs["owner"]
        if User.objects.filter(email=new_email).exists():
            return EMAIL_ALREADY_EXIST
        raw_code = f"{secrets.randbelow(1000000):06d}"
        try:
            EmailChange.objects.filter(user=user).delete()
            change_code = EmailChange(user=user, new_email=new_email)
            change_code.set_code(raw_code)
            change_code.save()
            send_email_token(new_email, raw_code, "Confirm your new e-mail address")
        except Exception:
            # transaction.set_rollback(True)
            raise ServiceUnavailable()
        return CODE_SENT


class EmailChangeConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    def validate_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Invalid current password."))
        return value

    def save(self, **kwargs):
        code = self.validated_data["code"]
        user = kwargs["owner"]
        change_code = EmailChange.objects.filter(user=user).first()
        if not change_code:
            return CODE_DOESNT_EXIST
        if not change_code.verify(code):
            return INVALID_CODE
        user.email = change_code.new_email
        user.save(update_fields=["email", "updated_at"])
        change_code.mark_used()
        return EMAIL_CHANGE_SUCCESS


class EmailChangeVerifySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, required=True)

    def save(self, **kwargs):
        code = self.validated_data["code"]
        user = kwargs["owner"]
        change_code = EmailChange.objects.filter(user=user).first()
        if not change_code:
            return CODE_DOESNT_EXIST
        if not change_code.verify(code):
            return INVALID_CODE
        change_code.mark_used()
        return EMAIL_VERIFIED


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True, required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )


class LogoutSerializer(serializers.Serializer):
    pass
