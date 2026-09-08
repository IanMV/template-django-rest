import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.models.email_verification import EmailVerification
from core.utils.email_token_sender import send_email_token

User = get_user_model()


class BaseUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"


class UserListRetrieveSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ("id", "name", "email", "created_at")


class UserCreateSerializer(BaseUserSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    class Meta(BaseUserSerializer.Meta):
        fields = ("name", "email", "password")

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        user = User.objects.create_user(is_active=False, **validated_data)
        raw_code = f"{secrets.randbelow(1000000):06d}"
        verification = EmailVerification(user=user)
        verification.set_code(raw_code)
        verification.save()
        send_email_token(user.email, raw_code, "Verify your e-mail")
        return user


class UserPatchSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ("name",)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


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


class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField(required=True)


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


class PasswordResetVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, required=True)


class EmailChangeVerifySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, required=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True, required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )


class LogoutSerializer(serializers.Serializer):
    pass


class EmailVerificationConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, required=True)


class EmailVerificationVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, required=True)
