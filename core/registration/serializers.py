from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator
from rest_framework import serializers

from core.models.user import User


class RegistrationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class RegistrationConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(
        validators=[RegexValidator(r"\A[0-9]{6}\Z", message="Enter six digits.")],
        max_length=6,
        min_length=6,
        required=True,
        help_text="Six-digit code sent to the registration email.",
    )
    name = serializers.CharField(required=True, max_length=255)
    password = serializers.CharField(
        trim_whitespace=False,
        validators=[RegexValidator(r"\S", message="This field may not be blank.")],
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        validate_password(
            attrs["password"], user=User(email=attrs["email"], name=attrs["name"])
        )
        return attrs
