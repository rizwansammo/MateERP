from rest_framework import serializers

from ..models import (
    Account,
    AccountingPeriod,
    ExchangeRate,
    FiscalYear,
    JournalEntry,
    JournalLine,
    TaxCode,
    TaxRevision,
)


class DecimalText(serializers.CharField):
    def to_internal_value(self, data):
        if isinstance(data, float | bool):
            raise serializers.ValidationError("Send exact amounts as decimal strings.")
        return super().to_internal_value(data)


class AccountSerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(allow_null=True, required=False)

    class Meta:
        model = Account
        fields = [
            "id",
            "code",
            "name",
            "account_type",
            "subtype",
            "parent_id",
            "normal_side",
            "description",
            "is_active",
            "is_postable",
            "currency",
            "control",
        ]
        extra_kwargs = {"normal_side": {"required": False}, "control": {"required": False}}


class LineInput(serializers.Serializer):
    account_id = serializers.IntegerField()
    currency = serializers.CharField(max_length=3, required=False)
    description = serializers.CharField(max_length=300, required=False, allow_blank=True)
    debit = DecimalText(required=False, default="0")
    credit = DecimalText(required=False, default="0")
    exchange_rate = DecimalText(required=False)
    rate_source = serializers.CharField(max_length=200, required=False, allow_blank=True)
    dimensions = serializers.DictField(required=False)
    tax_revision_id = serializers.IntegerField(required=False, allow_null=True)


class JournalInput(serializers.Serializer):
    posting_date = serializers.DateField()
    journal_date = serializers.DateField(required=False)
    description = serializers.CharField(max_length=500)
    kind = serializers.ChoiceField(choices=["manual", "opening", "adjustment"], required=False)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    adjustment_of = serializers.UUIDField(required=False, allow_null=True)
    revision = serializers.IntegerField(required=False)
    lines = LineInput(many=True, min_length=1, max_length=250)


class LineSerializer(serializers.ModelSerializer):
    account_id = serializers.IntegerField()
    account_name = serializers.CharField(source="account.name")
    account_code = serializers.CharField(source="account.code")

    class Meta:
        model = JournalLine
        fields = [
            "id",
            "position",
            "account_id",
            "account_name",
            "account_code",
            "description",
            "currency",
            "debit",
            "credit",
            "exchange_rate",
            "rate_source",
            "base_debit",
            "base_credit",
            "valuation",
            "account_snapshot",
            "dimensions",
            "tax_revision_id",
        ]


class JournalSerializer(serializers.ModelSerializer):
    lines = LineSerializer(many=True)
    created_by_name = serializers.CharField(source="created_by.get_username")
    reversed_by_id = serializers.SerializerMethodField()
    approval_id = serializers.IntegerField(allow_null=True)
    approval_status = serializers.CharField(
        source="approval.status", allow_null=True, read_only=True
    )

    def get_reversed_by_id(self, obj) -> str | None:
        return str(obj.reversed_by.pk) if hasattr(obj, "reversed_by") else None

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "number",
            "journal_date",
            "posting_date",
            "description",
            "status",
            "kind",
            "source_type",
            "source_id",
            "source_action",
            "base_currency",
            "period_id",
            "reversal_of_id",
            "reversed_by_id",
            "adjustment_of_id",
            "reason",
            "revision",
            "created_by_name",
            "created_at",
            "posted_at",
            "approval_id",
            "approval_status",
            "lines",
        ]


class YearSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalYear
        fields = "__all__"


class PeriodSerializer(serializers.ModelSerializer):
    entry_count = serializers.SerializerMethodField()
    revenue = serializers.SerializerMethodField()
    expenses = serializers.SerializerMethodField()
    closed_by_name = serializers.SerializerMethodField()

    def get_entry_count(self, obj) -> int:
        return obj.journalentry_set.filter(status="posted").count()

    def get_revenue(self, obj) -> str:
        from ..reports import report

        return report("pnl", obj.start, obj.end)["revenue"]

    def get_expenses(self, obj) -> str:
        from ..reports import report

        return report("pnl", obj.start, obj.end)["expenses"]

    def get_closed_by_name(self, obj) -> str:
        return obj.closed_by.get_username() if obj.closed_by else ""

    class Meta:
        model = AccountingPeriod
        fields = "__all__"


class RateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRate
        fields = "__all__"
        read_only_fields = ["base_currency", "created_by", "created_at"]


class RateInput(serializers.Serializer):
    currency = serializers.CharField(max_length=3)
    effective_date = serializers.DateField()
    value = DecimalText()
    source = serializers.CharField(max_length=200)


class ConversionInput(serializers.Serializer):
    currency = serializers.CharField(max_length=3)
    on = serializers.DateField()
    amount = DecimalText()


class TaxRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRevision
        fields = "__all__"


class TaxSerializer(serializers.ModelSerializer):
    revisions = TaxRevisionSerializer(many=True, read_only=True)

    class Meta:
        model = TaxCode
        fields = ["id", "code", "name", "description", "is_active", "revisions"]


class TaxRevisionInput(serializers.Serializer):
    effective_date = serializers.DateField()
    percent = DecimalText()
    input_account_id = serializers.IntegerField()
    output_account_id = serializers.IntegerField()


class TaxInput(serializers.Serializer):
    code = serializers.CharField(max_length=24)
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, max_length=500)
    is_active = serializers.BooleanField(required=False)
    revision = TaxRevisionInput(required=False)


class DateInput(serializers.Serializer):
    start = serializers.DateField()


class DecisionInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    posting_date = serializers.DateField(required=False)
    posting_key = serializers.CharField(max_length=160, required=False)


class EnvelopeSerializer(serializers.Serializer):
    """Variable report/action objects; documented properties live in the posting contract."""

    data = serializers.JSONField(required=False)
