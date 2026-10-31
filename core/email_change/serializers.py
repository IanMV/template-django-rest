from django.core.validators import RegexValidator
from rest_framework import serializers


class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField(required=True)
    password = serializers.CharField(
        trim_whitespace=False,
        validators=[RegexValidator(r"\S", message="This field may not be blank.")],
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Current account password.",
    )


class EmailChangeVerifySerializer(serializers.Serializer):
    code = serializers.CharField(
        max_length=6,
        min_length=6,
        required=True,
        help_text="Six-digit code sent to the new email address.",
    )


class EmailChangeConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(
        max_length=6,
        min_length=6,
        required=True,
        help_text="Six-digit code sent to the new email address.",
    )
    password = serializers.CharField(
        trim_whitespace=False,
        validators=[RegexValidator(r"\S", message="This field may not be blank.")],
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Current account password.",
    )
