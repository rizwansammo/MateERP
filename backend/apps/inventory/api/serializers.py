from rest_framework import serializers

from apps.accounting.api.serializers import DecimalText

from ..models import Location, Movement, StockCount


class StockCountSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockCount
        fields = [
            "id",
            "payload",
            "basis",
            "key",
            "status",
            "approval_id",
            "movement_id",
            "created_by_id",
            "created_at",
        ]


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "code", "name", "address", "is_active"]
        extra_kwargs = {"code": {"validators": []}}


class MovementSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name")
    item_code = serializers.CharField(source="item.code")
    location_name = serializers.CharField(source="location.name")

    class Meta:
        model = Movement
        fields = [
            "id",
            "sequence",
            "item_id",
            "item_name",
            "item_code",
            "location_id",
            "location_name",
            "date",
            "kind",
            "quantity",
            "base_value",
            "source_type",
            "source_id",
            "source_key",
            "reason",
            "original_id",
            "journal_id",
            "created_at",
            "created_by_id",
        ]


class AdjustmentInput(serializers.Serializer):
    item_id = serializers.IntegerField()
    location_id = serializers.IntegerField()
    date = serializers.DateField()
    quantity = DecimalText()
    expected_quantity = DecimalText()
    base_value = DecimalText(required=False)
    offset_account_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)
    key = serializers.CharField(min_length=8, max_length=140)
    kind = serializers.ChoiceField(choices=["count", "valuation"], required=False)
    correction_of_id = serializers.UUIDField(required=False)


class TransferInput(serializers.Serializer):
    item_id = serializers.IntegerField()
    from_location_id = serializers.IntegerField()
    to_location_id = serializers.IntegerField()
    date = serializers.DateField()
    quantity = DecimalText()
    reason = serializers.CharField(max_length=500)
    key = serializers.CharField(min_length=8, max_length=140)


class PositionInput(serializers.Serializer):
    item_id = serializers.IntegerField()
    location_id = serializers.IntegerField(required=False)
    date = serializers.DateField(required=False)


class PositionSerializer(serializers.Serializer):
    quantity = DecimalText()
    value = DecimalText()
    average_cost = DecimalText()


class ReconciliationSerializer(serializers.Serializer):
    currency = serializers.CharField()
    stock_value = DecimalText()
    gl_value = DecimalText()
    difference = DecimalText()
    date = serializers.DateField(allow_null=True)


class ValuationRowSerializer(PositionSerializer):
    id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    unit = serializers.CharField()
    reorder_level = DecimalText()


class ValuationSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = ValuationRowSerializer(many=True)
    reconciliation = ReconciliationSerializer()
