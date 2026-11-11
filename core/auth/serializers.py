from django.core.validators import RegexValidator
from rest_framework import serializers

from core.shared.passwords import MAX_PASSWORD_LENGTH
from core.shared.serializers import CanonicalEmailField


class LoginSerializer(serializers.Serializer):
    email = CanonicalEmailField(max_length=254)
    password = serializers.CharField(
        max_length=MAX_PASSWORD_LENGTH,
        trim_whitespace=False,
        validators=[RegexValidator(r"\S", message="This field may not be blank.")],
        write_only=True,
        style={"input_type": "password"},
    )


class CsrfSerializer(serializers.Serializer):
    csrfToken = serializers.CharField(read_only=True)


class LoginResponseSerializer(CsrfSerializer):
    detail = serializers.CharField(read_only=True)
