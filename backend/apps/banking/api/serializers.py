from rest_framework import serializers

from apps.accounting.api.serializers import DecimalText, LineSerializer
from apps.accounting.services.posting import bank_position
from apps.accounts.authorization import has_perm

from ..models import BankAccount


class BankInput(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    kind = serializers.ChoiceField(choices=["bank", "cash"])
    institution = serializers.CharField(max_length=160, required=False, allow_blank=True)
    identifier = serializers.CharField(max_length=120, required=False, allow_blank=True)
    currency = serializers.CharField(max_length=3)
    gl_account_id = serializers.IntegerField()
    is_active = serializers.BooleanField(required=False)


class BankSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()
    book_value = serializers.SerializerMethodField()
    identifier = serializers.SerializerMethodField()
    gl_account_id = serializers.IntegerField()

    def get_balance(self, obj) -> str:
        return str(bank_position(obj.gl_account_id)[0])

    def get_book_value(self, obj) -> str:
        return str(bank_position(obj.gl_account_id)[1])

    def get_identifier(self, obj) -> str:
        request = self.context.get("request")
        if (
            request
            and self.context.get("detail")
            and has_perm(request.user, "banking.evidence.view")
        ):
            return obj.identifier
        return "••••" + obj.identifier[-4:] if obj.identifier else ""

    class Meta:
        model = BankAccount
        fields = [
            "id",
            "name",
            "kind",
            "institution",
            "identifier",
            "currency",
            "gl_account_id",
            "is_active",
            "balance",
            "book_value",
        ]


class TreasuryInput(serializers.Serializer):
    posting_key = serializers.CharField(min_length=8, max_length=160)
    bank_account_id = serializers.IntegerField()
    kind = serializers.ChoiceField(
        choices=[
            "transfer",
            "deposit",
            "withdrawal",
            "charge",
            "interest",
            "adjustment_in",
            "adjustment_out",
        ]
    )
    posting_date = serializers.DateField()
    amount = DecimalText()
    received_amount = DecimalText(required=False)
    destination_id = serializers.IntegerField(required=False)
    counter_account_id = serializers.IntegerField(required=False)
    description = serializers.CharField(max_length=500)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    confirm_fx = serializers.BooleanField(required=False)
    quote_fingerprint = serializers.CharField(required=False, min_length=64, max_length=64)


class StatementLineInput(serializers.Serializer):
    date = serializers.DateField()
    description = serializers.CharField(max_length=300)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    amount = DecimalText()


class StatementInput(serializers.Serializer):
    bank_account_id = serializers.IntegerField()
    reference = serializers.CharField(max_length=120)
    start = serializers.DateField()
    end = serializers.DateField()
    opening_balance = DecimalText()
    closing_balance = DecimalText()
    lines = StatementLineInput(many=True, min_length=0, max_length=500)


class MatchInput(serializers.Serializer):
    statement_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=100
    )
    ledger_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=100
    )


class BankLineSerializer(LineSerializer):
    date = serializers.DateField(source="journal.posting_date")
    number = serializers.CharField(source="journal.number")
    source = serializers.CharField(source="journal.source_type")
    journal_id = serializers.UUIDField()
    matched = serializers.SerializerMethodField()

    def get_matched(self, obj) -> bool:
        return obj.matches.filter(is_active=True).exists()

    class Meta(LineSerializer.Meta):
        fields = [*LineSerializer.Meta.fields, "date", "number", "source", "journal_id", "matched"]
