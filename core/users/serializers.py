from django.core.validators import RegexValidator
from rest_framework import serializers

from core.models.user import User
from core.shared.passwords import MAX_PASSWORD_LENGTH


class UserListRetrieveSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "name", "email", "created_at")


class DeactivateSelfSerializer(serializers.Serializer):
    password = serializers.CharField(
        max_length=MAX_PASSWORD_LENGTH,
        trim_whitespace=False,
        validators=[RegexValidator(r"\S", message="This field may not be blank.")],
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Current account password.",
    )
