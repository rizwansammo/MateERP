from rest_framework import serializers

from apps.accounts.api.serializers import RoleRefSerializer
from apps.accounts.models import Role
from apps.approvals.catalog import BY_KEY
from apps.approvals.models import ApprovalPolicy, ApprovalRequest


class ApprovalPolicySerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    phase = serializers.SerializerMethodField()
    enforced = serializers.SerializerMethodField()
    supports_threshold = serializers.SerializerMethodField()
    approver_role = RoleRefSerializer(read_only=True)

    class Meta:
        model = ApprovalPolicy
        fields = [
            "category",
            "label",
            "description",
            "phase",
            "enforced",
            "supports_threshold",
            "is_required",
            "is_active",
            "approver_role",
            "amount_threshold",
            "allow_self_approval",
            "notes",
            "updated_at",
        ]
        read_only_fields = fields

    def get_label(self, obj) -> str:
        return BY_KEY[obj.category].label

    def get_description(self, obj) -> str:
        return BY_KEY[obj.category].description

    def get_phase(self, obj) -> int:
        return BY_KEY[obj.category].phase

    def get_enforced(self, obj) -> bool:
        return BY_KEY[obj.category].enforced

    def get_supports_threshold(self, obj) -> bool:
        return BY_KEY[obj.category].supports_threshold


class ApprovalPolicyUpdateSerializer(serializers.Serializer):
    is_required = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)
    approver_role = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), allow_null=True, required=False
    )
    amount_threshold = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, allow_null=True, required=False
    )
    allow_self_approval = serializers.BooleanField(required=False)
    notes = serializers.CharField(max_length=500, allow_blank=True, required=False)


class PersonSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    display_name = serializers.CharField()


class ApprovalRequestSerializer(serializers.ModelSerializer):
    requested_by = PersonSerializer(read_only=True)
    reviewed_by = PersonSerializer(read_only=True, allow_null=True)
    can_decide = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = [
            "id",
            "category",
            "action",
            "title",
            "status",
            "requested_by",
            "requested_at",
            "request_reason",
            "reviewed_by",
            "reviewed_at",
            "decision_reason",
            "result_reference",
            "can_decide",
            "summary",
        ]
        read_only_fields = fields

    def get_can_decide(self, obj) -> bool:
        from apps.approvals.services import can_decide

        user = self.context.get("user")
        return bool(user) and can_decide(user, obj)[0]

    def get_summary(self, obj) -> dict:
        # Only non-sensitive descriptive fields of the captured payload.
        payload = obj.payload or {}
        if obj.action == "accounting.post":
            return {"journal_id": payload.get("journal_id", "")}
        targets = {
            "invoice.approve": ("invoice_id", "/sales/invoices/"),
            "payment.verify": ("payment_id", "/sales/payments/"),
            "credit_note.issue": ("credit_note_id", "/sales/credits"),
            "refund.pay": ("refund_id", "/sales/credits"),
            "vendor_bill.post": ("bill_id", "/purchases/bills/"),
            "expense.post": ("expense_id", "/purchases/expenses/"),
            "vendor_payment.post": ("payment_id", "/purchases/payments/"),
        }
        if obj.action in targets:
            key, prefix = targets[obj.action]
            pk = payload.get(key)
            return (
                {"record_url": f"{prefix}{pk}/" if prefix.endswith("/") else prefix} if pk else {}
            )
        return {k: payload[k] for k in ("label", "template", "receipt_template") if k in payload}


class DecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=True, default="")
