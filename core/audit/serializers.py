from rest_framework import serializers

from core.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = (
            "id",
            "created_at",
            "event_type",
            "status",
            "user_uuid_snapshot",
            "ip_address",
            "user_agent",
            "session_id",
            "details_json",
        )
