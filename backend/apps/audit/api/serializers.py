from rest_framework import serializers

from apps.audit.models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "occurred_at",
            "actor",
            "actor_label",
            "action",
            "category",
            "target_type",
            "target_id",
            "target_label",
            "request_id",
            "ip_address",
            "before",
            "after",
            "outcome",
            "reason",
        ]
        read_only_fields = fields
