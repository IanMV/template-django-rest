from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.models.user import UserManager


class CanonicalEmailField(serializers.EmailField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            return UserManager.normalize_email(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
