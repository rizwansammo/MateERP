from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.accounting.api.serializers import DecimalText
from apps.sales.api.serializers import ItemSerializer as LegacyItemSerializer

from ..models import Category, ItemProfile, PriceRevision, Unit


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "code", "name", "is_active"]
        extra_kwargs = {"code": {"validators": []}}


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "code", "name", "allows_fraction", "is_active"]
        extra_kwargs = {"code": {"validators": []}}


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemProfile
        fields = [
            "kind",
            "category_id",
            "unit_id",
            "purchase_account_id",
            "cogs_account_id",
            "inventory_account_id",
            "preferred_vendor_id",
            "reorder_level",
            "revision",
        ]


@extend_schema_serializer(component_name="CatalogItem")
class ItemSerializer(LegacyItemSerializer):
    profile = ProfileSerializer(read_only=True)

    class Meta(LegacyItemSerializer.Meta):
        fields = [*LegacyItemSerializer.Meta.fields, "profile"]


@extend_schema_serializer(component_name="CatalogItemInput")
class ItemInput(serializers.Serializer):
    code = serializers.CharField(max_length=40, required=False)
    name = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    currency = serializers.CharField(max_length=3, required=False)
    unit_price = DecimalText(required=False)
    kind = serializers.ChoiceField(choices=ItemProfile.Kind.choices, required=False)
    unit_id = serializers.IntegerField(required=False)
    category_id = serializers.IntegerField(required=False, allow_null=True)
    purchase_account_id = serializers.IntegerField(required=False, allow_null=True)
    cogs_account_id = serializers.IntegerField(required=False, allow_null=True)
    inventory_account_id = serializers.IntegerField(required=False, allow_null=True)
    revenue_account_id = serializers.IntegerField(required=False, allow_null=True)
    tax_code_id = serializers.IntegerField(required=False, allow_null=True)
    preferred_vendor_id = serializers.IntegerField(required=False, allow_null=True)
    reorder_level = DecimalText(required=False)
    revision = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)


class PriceSerializer(serializers.ModelSerializer):
    value = DecimalText()

    class Meta:
        model = PriceRevision
        fields = [
            "id",
            "purpose",
            "effective_date",
            "currency",
            "value",
            "includes_tax",
            "reason",
            "created_at",
            "created_by_id",
        ]
        read_only_fields = ["id", "created_at", "created_by_id"]


@extend_schema_serializer(component_name="CatalogQuoteInput")
class QuoteInput(serializers.Serializer):
    date = serializers.DateField()
    currency = serializers.CharField(max_length=3)
    purpose = serializers.ChoiceField(
        choices=[("sale", "Sale"), ("purchase", "Purchase")], default="sale"
    )
    quantity = DecimalText(default="1")


class MarginInput(serializers.Serializer):
    date = serializers.DateField()
    currency = serializers.CharField(max_length=3)
    sale = DecimalText()
    cost = DecimalText()


@extend_schema_serializer(component_name="CatalogQuote")
class QuoteSerializer(QuoteInput):
    item_id = serializers.IntegerField()
    unit_price = DecimalText()
    subtotal = DecimalText()
    includes_tax = serializers.BooleanField()
    price_revision_id = serializers.IntegerField(allow_null=True)
    basis = serializers.CharField()


class MarginSerializer(MarginInput):
    item_id = serializers.IntegerField()
    margin = DecimalText()
    percent = DecimalText(allow_null=True)
    realized = serializers.BooleanField()
