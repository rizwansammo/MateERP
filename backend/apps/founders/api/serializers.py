from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers as s

from apps.accounting.money import strings
from apps.company.models import FinancialParty
from apps.files.api.serializers import StoredFileSerializer

from .. import models as m


class PartySerializer(s.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        from apps.accounts.authorization import get_permission_codes

        request = self.context.get("request")
        if request and not {
            "founder.view",
            "ownership.view",
            "ownership.manage",
        } & get_permission_codes(request.user):
            data = {
                key: value
                for key, value in data.items()
                if key
                in {
                    "id",
                    "name",
                    "display_name",
                    "user",
                    "kind",
                    "is_founder",
                    "is_shareholder",
                    "is_partner",
                    "is_active",
                    "joined",
                    "left",
                }
            }
        return data

    class Meta:
        model = FinancialParty
        fields = "__all__"
        read_only_fields = ["id", "created_at"]


class PartyInput(PartySerializer):
    user_id = s.IntegerField(allow_null=True, required=False)

    class Meta(PartySerializer.Meta):
        exclude = None
        fields = [
            "name",
            "display_name",
            "kind",
            "email",
            "phone",
            "country",
            "notes",
            "user_id",
            "is_founder",
            "is_shareholder",
            "is_partner",
            "is_active",
            "joined",
            "left",
        ]


class LoanSerializer(s.ModelSerializer):
    class Meta:
        model = m.FounderLoan
        fields = "__all__"
        read_only_fields = ["id", "created_by"]


class LoanInput(s.Serializer):
    party_id = s.IntegerField(min_value=1)
    name = s.CharField(max_length=160)
    currency = s.CharField(max_length=3)
    terms = s.CharField(max_length=2000, allow_blank=True, required=False)
    maturity = s.DateField(allow_null=True, required=False)
    reference = s.CharField(max_length=120, allow_blank=True, required=False)


@extend_schema_serializer(component_name="FounderObligationAllocationInput")
class AllocationInput(s.Serializer):
    obligation_id = s.IntegerField(min_value=1)
    amount = s.DecimalField(max_digits=24, decimal_places=6)


@extend_schema_serializer(component_name="FounderVendorAllocationInput")
class VendorAllocationInput(s.Serializer):
    bill_id = s.IntegerField(min_value=1, required=False)
    expense_id = s.IntegerField(min_value=1, required=False)
    amount = s.DecimalField(max_digits=24, decimal_places=6)


class CorporateInput(s.Serializer):
    client_key = s.CharField(min_length=8, max_length=160)
    kind = s.ChoiceField(
        choices=[k for k, _ in m.CorporateTransaction._meta.get_field("kind").choices]
    )
    classification = s.ChoiceField(
        choices=[k for k, _ in m.CorporateTransaction._meta.get_field("classification").choices]
    )
    party_id = s.IntegerField(min_value=1)
    recipient_id = s.IntegerField(min_value=1, required=False, allow_null=True)
    date = s.DateField()
    currency = s.CharField(max_length=3)
    amount = s.DecimalField(max_digits=24, decimal_places=6, required=False)
    bank_id = s.IntegerField(min_value=1, allow_null=True, required=False)
    loan_id = s.IntegerField(min_value=1, allow_null=True, required=False)
    issuance_id = s.IntegerField(min_value=1, allow_null=True, required=False)
    reference = s.CharField(max_length=120, allow_blank=True, required=False)
    notes = s.CharField(max_length=2000, allow_blank=True, required=False)
    expense = s.DictField(required=False)
    allocations = AllocationInput(many=True, required=False)
    vendor_allocations = VendorAllocationInput(many=True, required=False)

    def validate(self, data):
        if data["kind"] == "expense":
            # The purchasing service validates and calculates this source. Use
            # explicit fields rather than forwarding arbitrary JSON to models.
            permitted = {
                "description",
                "vendor_id",
                "account_id",
                "amount",
                "tax_code_id",
                "prices_include_tax",
                "project_id",
                "notes",
            }
            if not data.get("expense") or set(data["expense"]) - permitted:
                raise s.ValidationError({"expense": "Provide supported expense fields."})
            positive_amount = data["expense"].get("amount")
            if positive_amount is None:
                raise s.ValidationError({"expense": "An expense amount is required."})
        elif "amount" not in data:
            raise s.ValidationError({"amount": "This transaction requires an amount."})
        return data


class CorporateSerializer(s.ModelSerializer):
    party_name = s.CharField(source="party.name", read_only=True)

    class Meta:
        model = m.CorporateTransaction
        fields = "__all__"
        read_only_fields = [f.name for f in m.CorporateTransaction._meta.fields]


class QuoteInput(s.Serializer):
    quote_fingerprint = s.CharField(max_length=64, required=False)
    confirm_fx = s.BooleanField(default=False)


@extend_schema_serializer(component_name="FounderReasonInput")
class ReasonInput(s.Serializer):
    reason = s.CharField(max_length=1000)
    date = s.DateField(required=False)


class ConfirmationInput(s.Serializer):
    party_id = s.IntegerField(min_value=1)
    mode = s.ChoiceField(choices=["authenticated", "attestation"])
    reference = s.CharField(max_length=500, allow_blank=True, default="")


class PolicySerializer(s.ModelSerializer):
    class Meta:
        model = m.SharingPolicy
        fields = "__all__"


class PolicyInput(s.Serializer):
    name = s.CharField(max_length=160)
    effective_from = s.DateField()
    effective_until = s.DateField(required=False, allow_null=True)
    category_id = s.IntegerField(min_value=1, required=False, allow_null=True)
    basis = s.ChoiceField(choices=["equal", "custom", "provisional", "formal"])
    weights = s.DictField(child=s.CharField(), required=False)


class SharedExpenseSerializer(s.ModelSerializer):
    class Meta:
        model = m.SharedExpense
        fields = "__all__"


class SharedExpenseInput(s.Serializer):
    expense_id = s.IntegerField(min_value=1, required=False)
    founder_payment_id = s.IntegerField(min_value=1, required=False)
    payer_id = s.IntegerField(min_value=1, required=False)
    date = s.DateField(required=False)
    currency = s.CharField(max_length=3, required=False)
    amount = s.DecimalField(max_digits=24, decimal_places=6, required=False)
    description = s.CharField(max_length=300, required=False)
    category_id = s.IntegerField(required=False)

    def validate(self, data):
        if not data.get("expense_id") and not data.get("founder_payment_id"):
            for key in ("payer_id", "date", "currency", "amount", "description"):
                if key not in data:
                    raise s.ValidationError({key: "Required for a personal-only expense."})
        return data


class PersonalSerializer(s.ModelSerializer):
    payer_name = s.CharField(source="payer.name", read_only=True)
    recipient_name = s.CharField(source="recipient.name", read_only=True)
    confirmations = s.SerializerMethodField()
    allocations = s.SerializerMethodField()

    class Meta:
        model = m.PersonalSettlement
        fields = "__all__"

    def get_confirmations(self, obj) -> list:
        return list(obj.confirmations.values("party_id", "actor_id", "mode", "reference"))

    def get_allocations(self, obj) -> list:
        return strings(list(obj.allocations.values("obligation_id", "amount")))


class PersonalInput(s.Serializer):
    client_key = s.CharField(min_length=8, max_length=160)
    payer_id = s.IntegerField(min_value=1)
    recipient_id = s.IntegerField(min_value=1)
    date = s.DateField()
    currency = s.CharField(max_length=3)
    amount = s.DecimalField(max_digits=24, decimal_places=6)
    reference = s.CharField(max_length=120, allow_blank=True, required=False)
    notes = s.CharField(max_length=2000, allow_blank=True, required=False)
    returns_id = s.IntegerField(min_value=1, required=False)
    allocations = AllocationInput(many=True)


class ForecastInput(s.Serializer):
    name = s.CharField(max_length=160, default="Funding forecast")
    starts = s.DateField()
    months = s.IntegerField(min_value=1, max_value=24, default=12)
    mode = s.ChoiceField(choices=["founders", "partial", "self_sustaining"], default="founders")
    previous_id = s.IntegerField(min_value=1, required=False)
    schedule_ids = s.ListField(child=s.IntegerField(min_value=1), required=False, max_length=100)
    expense_ids = s.ListField(child=s.IntegerField(min_value=1), required=False, max_length=100)
    bill_ids = s.ListField(child=s.IntegerField(min_value=1), required=False, max_length=100)


class PlanSerializer(s.ModelSerializer):
    class Meta:
        model = m.FundingPlan
        fields = "__all__"


class ReserveSerializer(s.ModelSerializer):
    progress = s.SerializerMethodField()

    class Meta:
        model = m.AnnualReserve
        fields = "__all__"

    def get_progress(self, obj) -> dict:
        from ..services.planning import reserve_stats

        return strings(reserve_stats(obj))


class ReserveInput(s.Serializer):
    reason = s.CharField(max_length=1000, required=False, allow_blank=True)
    name = s.CharField(max_length=160)
    schedule_id = s.IntegerField(min_value=1)
    starts = s.DateField()
    renewal = s.DateField()
    target = s.DecimalField(max_digits=24, decimal_places=6)
    previous_id = s.IntegerField(min_value=1, required=False)


class DesignationSerializer(s.ModelSerializer):
    currency = s.CharField(source="receipt.currency", read_only=True)
    remaining = s.SerializerMethodField()
    consumptions = s.SerializerMethodField()

    class Meta:
        model = m.FundingDesignation
        fields = "__all__"

    def get_remaining(self, obj) -> str:
        from ..services.planning import retained

        return str(retained(m.FundingDesignation.objects.filter(pk=obj.pk)))

    def get_consumptions(self, obj) -> list:
        from ..services.planning import active_consumptions

        return strings(
            list(active_consumptions().filter(designation=obj).values("id", "expense_id", "amount"))
        )


class DesignationInput(s.Serializer):
    receipt_id = s.IntegerField(min_value=1)
    plan_id = s.IntegerField(min_value=1, required=False)
    reserve_id = s.IntegerField(min_value=1, required=False)
    month = s.DateField()
    amount = s.DecimalField(max_digits=24, decimal_places=6)


class PledgeSerializer(s.ModelSerializer):
    class Meta:
        model = m.FundingPledge
        fields = "__all__"


class PledgeInput(s.Serializer):
    plan_id = s.IntegerField(min_value=1)
    party_id = s.IntegerField(min_value=1)
    month = s.DateField()
    currency = s.CharField(max_length=3)
    amount = s.DecimalField(max_digits=24, decimal_places=6)
    status = s.ChoiceField(choices=["requested", "promised", "cancelled"], default="requested")
    reference = s.CharField(max_length=200, allow_blank=True, default="")


class PledgeStatusInput(s.Serializer):
    status = s.ChoiceField(choices=["promised", "cancelled"])
    reason = s.CharField(max_length=1000)


class EvidenceInput(s.Serializer):
    title = s.CharField(max_length=200)
    party_id = s.IntegerField(required=False)
    proposal_id = s.IntegerField(required=False)
    transaction_id = s.IntegerField(required=False)
    settlement_id = s.IntegerField(required=False)
    loan_id = s.IntegerField(required=False)
    file = s.FileField()


class EvidenceSerializer(s.ModelSerializer):
    file = StoredFileSerializer(read_only=True)

    class Meta:
        model = m.FounderEvidence
        fields = "__all__"


class ResolutionInput(s.Serializer):
    obligation_id = s.IntegerField(min_value=1)
    settlement_id = s.IntegerField(min_value=1)
    corporate_transaction_id = s.IntegerField(min_value=1)
    amount = s.DecimalField(max_digits=24, decimal_places=6)
    reason = s.CharField(max_length=1000)


class ResolutionSerializer(s.ModelSerializer):
    class Meta:
        model = m.RecoveryResolution
        fields = "__all__"


class ConsumeInput(s.Serializer):
    expense_id = s.IntegerField(min_value=1)
    amount = s.DecimalField(max_digits=24, decimal_places=6, required=False)


class ReleaseInput(s.Serializer):
    amount = s.DecimalField(max_digits=24, decimal_places=6)
    reason = s.CharField(max_length=1000)
    client_key = s.CharField(min_length=8, max_length=160)


class CompanyCoverageSerializer(s.ModelSerializer):
    currency = s.CharField(source="bank.currency", read_only=True)

    class Meta:
        model = m.CompanyFundingCoverage
        fields = "__all__"


class CompanyCoverageInput(s.Serializer):
    plan_id = s.IntegerField(min_value=1)
    bank_id = s.IntegerField(min_value=1)
    month = s.DateField()
    amount = s.DecimalField(max_digits=24, decimal_places=6)
    reference = s.CharField(max_length=500)


class CoverageDecisionInput(s.Serializer):
    expense_id = s.IntegerField(min_value=1, required=False)
    reason = s.CharField(max_length=1000, required=False)


class ConsumptionSerializer(s.ModelSerializer):
    class Meta:
        model = m.FundingConsumption
        fields = "__all__"
