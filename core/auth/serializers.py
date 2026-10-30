from rest_framework import serializers

from core.models.user import UserSession


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True, required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )


class UserSessionSerializer(serializers.ModelSerializer):
    device = serializers.CharField(source="device_name", read_only=True)
    ip = serializers.CharField(source="ip_address", read_only=True)
    current = serializers.BooleanField(
        read_only=True, help_text="Whether this is the session making the request."
    )

    class Meta:
        model = UserSession
        fields = ["id", "device", "ip", "created_at", "current"]
