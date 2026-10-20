from rest_framework import serializers


class CheckResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "unavailable"])
    latency_ms = serializers.FloatField(allow_null=True)


class HealthChecksSerializer(serializers.Serializer):
    database = CheckResultSerializer()


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "unavailable"])
    service = serializers.CharField()
    version = serializers.CharField()
    environment = serializers.CharField()
    time = serializers.DateTimeField()
    checks = HealthChecksSerializer()
