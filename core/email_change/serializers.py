from django.core.validators import RegexValidator
from rest_framework import serializers

from core.shared.passwords import MAX_PASSWORD_LENGTH
from core.shared.serializers import CanonicalEmailField


class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = CanonicalEmailField(required=True, max_length=254)
    password = serializers.CharField(
        max_length=MAX_PASSWORD_LENGTH,
        trim_whitespace=False,
        validators=[RegexValidator(r"\S", message="This field may not be blank.")],
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Current account password.",
    )


class EmailChangeConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(
        validators=[RegexValidator(r"\A[0-9]{6}\Z", message="Enter six digits.")],
        max_length=6,
        min_length=6,
        required=True,
        help_text="Six-digit code sent to the new email address.",
    )
    password = serializers.CharField(
        max_length=MAX_PASSWORD_LENGTH,
        trim_whitespace=False,
        validators=[RegexValidator(r"\S", message="This field may not be blank.")],
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Current account password.",
    )
