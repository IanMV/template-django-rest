from django.core.validators import RegexValidator
from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        trim_whitespace=False,
        validators=[RegexValidator(r"\S", message="This field may not be blank.")],
        write_only=True,
        style={"input_type": "password"},
    )


class CsrfSerializer(serializers.Serializer):
    csrfToken = serializers.CharField(read_only=True)


class LoginResponseSerializer(CsrfSerializer):
    detail = serializers.CharField(read_only=True)
