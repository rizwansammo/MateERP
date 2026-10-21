from rest_framework import serializers

from apps.accounting.api.serializers import DecimalText
from apps.billing.api.serializers import journal_ref
from apps.sales.api.serializers import DISCOUNT_TYPES

from ..models import (
    METHODS,
    Expense,
    RecurringExpenseRun,
    RecurringExpenseSchedule,
    Vendor,
    VendorBill,
    VendorBillLine,
    VendorPayment,
    VendorPaymentAllocation,
)


class VendorSerializer(serializers.ModelSerializer):
    default_account_id = serializers.IntegerField(required=False, allow_null=True)
    code = serializers.CharField(read_only=True)

    class Meta:
        model = Vendor
        fields = [
            "id",
            "code",
            "name",
            "contact_name",
            "email",
            "phone",
            "address",
            "country",
            "currency",
            "payment_terms_days",
            "tax_id",
            "website",
            "default_account_id",
            "notes",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class BillLineSerializer(serializers.ModelSerializer):
    tax_code_id = serializers.IntegerField(allow_null=True)
    account_id = serializers.IntegerField()

    class Meta:
        model = VendorBillLine
        fields = [
            "id",
            "position",
            "description",
            "quantity",
            "unit_price",
            "discount_type",
            "discount_value",
            "tax_code_id",
            "account_id",
            "subtotal",
            "line_discount",
            "taxable",
            "tax",
            "total",
            "tax_rate",
        ]


class BillSerializer(serializers.ModelSerializer):
    vendor_id = serializers.IntegerField()
    vendor_name = serializers.CharField(source="vendor.name")
    project_id = serializers.IntegerField(allow_null=True)
    outstanding = serializers.DecimalField(max_digits=24, decimal_places=6, read_only=True)
    lines = BillLineSerializer(many=True, read_only=True)
    journal = serializers.SerializerMethodField()
    void_journal = serializers.SerializerMethodField()
    created_by = serializers.CharField(source="created_by.display_name")

    class Meta:
        model = VendorBill
        fields = [
            "id",
            "number",
            "status",
            "vendor_id",
            "vendor_name",
            "vendor_reference",
            "project_id",
            "bill_date",
            "due_date",
            "currency",
            "prices_include_tax",
            "notes",
            "subtotal",
            "line_discount",
            "taxable",
            "tax",
            "total",
            "amount_paid",
            "outstanding",
            "exchange_rate",
            "base_total",
            "revision",
            "approval_id",
            "journal",
            "void_journal",
            "void_reason",
            "created_by",
            "created_at",
            "posted_at",
            "lines",
        ]

    def get_journal(self, obj) -> dict | None:
        return journal_ref(obj.journal)

    def get_void_journal(self, obj) -> dict | None:
        return journal_ref(obj.void_journal)


class BillLineInput(serializers.Serializer):
    description = serializers.CharField(max_length=500)
    quantity = DecimalText(default="1")
    unit_price = DecimalText()
    discount_type = serializers.ChoiceField(choices=DISCOUNT_TYPES, default="percent")
    discount_value = DecimalText(default="0")
    tax_code_id = serializers.IntegerField(required=False, allow_null=True)
    account_id = serializers.IntegerField(required=False, allow_null=True)


class BillInput(serializers.Serializer):
    vendor_id = serializers.IntegerField(required=False)
    vendor_reference = serializers.CharField(max_length=80, required=False)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    bill_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, required=False)
    prices_include_tax = serializers.BooleanField(required=False)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    revision = serializers.IntegerField(required=False)
    lines = BillLineInput(many=True, required=False)


class ExpenseSerializer(serializers.ModelSerializer):
    vendor_id = serializers.IntegerField(allow_null=True)
    vendor_name = serializers.CharField(source="vendor.name", default=None)
    account_id = serializers.IntegerField()
    account_name = serializers.CharField(source="account.name")
    bank_account_id = serializers.IntegerField(allow_null=True)
    bank_account_name = serializers.CharField(source="bank_account.name", default=None)
    tax_code_id = serializers.IntegerField(allow_null=True)
    project_id = serializers.IntegerField(allow_null=True)
    outstanding = serializers.DecimalField(max_digits=24, decimal_places=6, read_only=True)
    journal = serializers.SerializerMethodField()
    void_journal = serializers.SerializerMethodField()
    created_by = serializers.CharField(source="created_by.display_name")
    recurring_schedule_id = serializers.IntegerField(allow_null=True)

    class Meta:
        model = Expense
        fields = [
            "id",
            "number",
            "status",
            "vendor_id",
            "vendor_name",
            "project_id",
            "expense_date",
            "original_transaction_date",
            "recognition_reason",
            "due_date",
            "description",
            "currency",
            "account_id",
            "account_name",
            "entered_amount",
            "prices_include_tax",
            "tax_code_id",
            "taxable",
            "tax",
            "total",
            "payment_mode",
            "bank_account_id",
            "bank_account_name",
            "method",
            "reference",
            "notes",
            "amount_paid",
            "outstanding",
            "exchange_rate",
            "base_total",
            "revision",
            "approval_id",
            "journal",
            "void_journal",
            "void_reason",
            "created_by",
            "created_at",
            "recurring_schedule_id",
        ]

    def get_journal(self, obj) -> dict | None:
        return journal_ref(obj.journal)

    def get_void_journal(self, obj) -> dict | None:
        return journal_ref(obj.void_journal)


class ExpenseInput(serializers.Serializer):
    vendor_id = serializers.IntegerField(required=False, allow_null=True)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    expense_date = serializers.DateField(required=False)
    original_transaction_date = serializers.DateField(required=False, allow_null=True)
    recognition_reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    description = serializers.CharField(max_length=300, required=False)
    currency = serializers.CharField(max_length=3, required=False)
    account_id = serializers.IntegerField(required=False, allow_null=True)
    amount = DecimalText(required=False)
    prices_include_tax = serializers.BooleanField(required=False)
    tax_code_id = serializers.IntegerField(required=False, allow_null=True)
    payment_mode = serializers.ChoiceField(choices=Expense.Mode.choices, required=False)
    bank_account_id = serializers.IntegerField(required=False, allow_null=True)
    method = serializers.ChoiceField(choices=METHODS, required=False)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    paid_by = serializers.CharField(required=False, default="company")
    revision = serializers.IntegerField(required=False)


class VendorAllocationInput(serializers.Serializer):
    bill_id = serializers.IntegerField(required=False, allow_null=True)
    expense_id = serializers.IntegerField(required=False, allow_null=True)
    amount = DecimalText()


class VendorPaymentInput(serializers.Serializer):
    vendor_id = serializers.IntegerField()
    bank_account_id = serializers.IntegerField()
    payment_date = serializers.DateField(required=False)
    amount = DecimalText()
    method = serializers.ChoiceField(choices=METHODS, default="bank_transfer")
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    allocations = VendorAllocationInput(many=True)
    quote_fingerprint = serializers.CharField(max_length=64, required=False)
    confirm_fx = serializers.BooleanField(default=False)


class VendorAllocationSerializer(serializers.ModelSerializer):
    document = serializers.SerializerMethodField()

    class Meta:
        model = VendorPaymentAllocation
        fields = ["bill_id", "expense_id", "document", "amount", "base_amount"]

    def get_document(self, obj) -> str:
        return (obj.bill or obj.expense).number


class VendorPaymentSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name")
    bank_account_name = serializers.CharField(source="bank_account.name")
    allocations = VendorAllocationSerializer(many=True, read_only=True)
    journal = serializers.SerializerMethodField()
    reversal_journal = serializers.SerializerMethodField()
    created_by = serializers.CharField(source="created_by.display_name")

    class Meta:
        model = VendorPayment
        fields = [
            "id",
            "number",
            "status",
            "vendor_id",
            "vendor_name",
            "bank_account_id",
            "bank_account_name",
            "payment_date",
            "currency",
            "amount",
            "base_amount",
            "method",
            "reference",
            "notes",
            "approval_id",
            "allocations",
            "journal",
            "reversal_journal",
            "created_by",
            "created_at",
        ]

    def get_journal(self, obj) -> dict | None:
        return journal_ref(obj.journal)

    def get_reversal_journal(self, obj) -> dict | None:
        return journal_ref(obj.reversal_journal)


class ExpenseScheduleSerializer(serializers.ModelSerializer):
    vendor_id = serializers.IntegerField()
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)

    class Meta:
        model = RecurringExpenseSchedule
        fields = [
            "id",
            "name",
            "vendor_id",
            "vendor_name",
            "currency",
            "frequency",
            "interval",
            "start_date",
            "end_date",
            "next_run_date",
            "reminder_days",
            "template",
            "status",
            "revision",
            "created_at",
        ]
        read_only_fields = ["next_run_date", "status", "revision", "created_at", "template"]


class ExpenseScheduleInput(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False)
    vendor_id = serializers.IntegerField(required=False)
    currency = serializers.CharField(max_length=3, required=False)
    frequency = serializers.ChoiceField(
        choices=RecurringExpenseSchedule.Frequency.choices, required=False
    )
    interval = serializers.IntegerField(min_value=1, max_value=24, required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False, allow_null=True)
    reminder_days = serializers.IntegerField(min_value=0, max_value=90, required=False)
    description = serializers.CharField(max_length=200, required=False)
    account_id = serializers.IntegerField(required=False, allow_null=True)
    amount = DecimalText(required=False)
    tax_code_id = serializers.IntegerField(required=False, allow_null=True)
    prices_include_tax = serializers.BooleanField(required=False)
    payment_mode = serializers.ChoiceField(choices=Expense.Mode.choices, required=False)
    bank_account_id = serializers.IntegerField(required=False, allow_null=True)
    method = serializers.ChoiceField(choices=METHODS, required=False)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class ExpenseRunSerializer(serializers.ModelSerializer):
    expense_number = serializers.CharField(source="expense.number", default=None)

    class Meta:
        model = RecurringExpenseRun
        fields = [
            "id",
            "occurrence_date",
            "status",
            "message",
            "expense_id",
            "expense_number",
            "created_at",
        ]
