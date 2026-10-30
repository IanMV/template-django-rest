from rest_framework import serializers

from core.models.user import User


class UserListRetrieveSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "name", "email", "created_at")
