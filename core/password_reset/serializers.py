from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from core.models.user import User


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class PasswordResetVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(
        max_length=6,
        min_length=6,
        required=True,
        help_text="Six-digit code sent to the account email.",
    )


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(
        max_length=6,
        min_length=6,
        required=True,
        help_text="Six-digit code sent to the account email.",
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        user = User.objects.filter(email=attrs["email"], is_active=True).first()
        validate_password(attrs["new_password"], user=user)
        return attrs
