from rest_framework import serializers

from core.models.user import User


class UserListRetrieveSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "name", "email", "created_at")


class DeactivateSelfSerializer(serializers.Serializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Current account password.",
    )
