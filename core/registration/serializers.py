from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from core.models.user import User


class RegistrationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class RegistrationVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, min_length=6, required=True, help_text="Six-digit code sent to the registration email.")


class RegistrationConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, min_length=6, required=True, help_text="Six-digit code sent to the registration email.")
    name = serializers.CharField(required=True, max_length=255)
    password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )

    def validate(self, attrs):
        validate_password(
            attrs["password"], user=User(email=attrs["email"], name=attrs["name"])
        )
        return attrs
