from rest_framework import serializers

from apps.accounting.api.serializers import DecimalText

from ..models import (
    BillingItem,
    Customer,
    CustomerContact,
    Milestone,
    Project,
    SalesOrder,
    SalesOrderLine,
)

DISCOUNT_TYPES = [("percent", "Percent"), ("fixed", "Fixed")]


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerContact
        fields = ["id", "name", "role", "email", "phone", "is_primary", "is_active"]


class CustomerSerializer(serializers.ModelSerializer):
    code = serializers.CharField(max_length=24, required=False)

    class Meta:
        model = Customer
        fields = [
            "id",
            "code",
            "name",
            "contact_name",
            "email",
            "phone",
            "tax_id",
            "address",
            "city",
            "country",
            "currency",
            "payment_terms_days",
            "notes",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["created_at"]
        extra_kwargs = {"code": {"validators": []}}


class CustomerDetailSerializer(CustomerSerializer):
    contacts = ContactSerializer(many=True, read_only=True)

    class Meta(CustomerSerializer.Meta):
        fields = [*CustomerSerializer.Meta.fields, "contacts"]


class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = ["id", "position", "name", "percent", "amount"]


class MilestoneInput(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    percent = DecimalText()


class ProjectSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField()
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    milestones = MilestoneSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "reference",
            "name",
            "customer_id",
            "customer_name",
            "currency",
            "contract_value",
            "status",
            "notes",
            "milestones",
        ]


class ProjectInput(serializers.Serializer):
    reference = serializers.CharField(max_length=40, required=False)
    name = serializers.CharField(max_length=200, required=False)
    customer_id = serializers.IntegerField(required=False)
    currency = serializers.CharField(max_length=3, required=False)
    contract_value = DecimalText(required=False)
    status = serializers.ChoiceField(choices=Project.Status.choices, required=False)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    milestones = MilestoneInput(many=True, required=False)


class ItemSerializer(serializers.ModelSerializer):
    revenue_account_id = serializers.IntegerField(required=False, allow_null=True)
    tax_code_id = serializers.IntegerField(required=False, allow_null=True)
    unit_price = DecimalText(required=False)

    class Meta:
        model = BillingItem
        fields = [
            "id",
            "code",
            "name",
            "description",
            "unit",
            "unit_price",
            "currency",
            "revenue_account_id",
            "tax_code_id",
            "is_active",
        ]
        extra_kwargs = {"code": {"validators": []}}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["unit_price"] = format(instance.unit_price.normalize(), "f")
        return data


class DocumentLineInput(serializers.Serializer):
    item_id = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    quantity = DecimalText(required=False, default="1")
    unit_price = DecimalText(required=False)
    discount_type = serializers.ChoiceField(choices=DISCOUNT_TYPES, default="percent")
    discount_value = DecimalText(required=False, default="0")
    tax_code_id = serializers.IntegerField(required=False, allow_null=True)


class OrderLineSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(allow_null=True)
    tax_code_id = serializers.IntegerField(allow_null=True)

    class Meta:
        model = SalesOrderLine
        fields = [
            "id",
            "position",
            "item_id",
            "description",
            "quantity",
            "unit_price",
            "discount_type",
            "discount_value",
            "tax_code_id",
        ]


class OrderSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField()
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    project_id = serializers.IntegerField(allow_null=True)
    lines = OrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = SalesOrder
        fields = [
            "id",
            "number",
            "customer_id",
            "customer_name",
            "project_id",
            "order_date",
            "currency",
            "title",
            "customer_reference",
            "prices_include_tax",
            "status",
            "notes",
            "tax",
            "total",
            "revision",
            "created_at",
            "confirmed_at",
            "cancelled_reason",
            "lines",
        ]


class OrderInput(serializers.Serializer):
    customer_id = serializers.IntegerField(required=False)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    order_date = serializers.DateField(required=False)
    currency = serializers.CharField(max_length=3, required=False)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    customer_reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    prices_include_tax = serializers.BooleanField(required=False)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    revision = serializers.IntegerField(required=False)
    lines = DocumentLineInput(many=True, required=False)


class CalculateInput(serializers.Serializer):
    currency = serializers.CharField(max_length=3)
    date = serializers.DateField()
    prices_include_tax = serializers.BooleanField(default=False)
    discount_type = serializers.ChoiceField(choices=DISCOUNT_TYPES, default="percent")
    discount_value = DecimalText(required=False, default="0")
    lines = DocumentLineInput(many=True)


class ReasonInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")
