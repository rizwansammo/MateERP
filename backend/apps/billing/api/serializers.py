from django.utils import timezone
from rest_framework import serializers

from apps.accounting.api.serializers import DecimalText
from apps.files.api.serializers import file_url
from apps.sales.api.serializers import DISCOUNT_TYPES, DocumentLineInput

from ..models import (
    CreditApplication,
    CreditNote,
    CustomerPayment,
    Invoice,
    InvoiceLine,
    LedgerSettings,
    MoneyReceipt,
    PaymentAllocation,
    RecurringInvoiceRun,
    RecurringInvoiceSchedule,
    Refund,
)


class JournalRef(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.CharField()


def journal_ref(journal):
    return {"id": str(journal.pk), "number": journal.number} if journal else None


class PdfMixin(serializers.Serializer):
    pdf_url = serializers.SerializerMethodField()

    def get_pdf_url(self, obj) -> str | None:
        return file_url(obj.pdf_file) if obj.pdf_status == "ready" else None


class InvoiceLineSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(allow_null=True)
    sales_order_line_id = serializers.IntegerField(allow_null=True)
    tax_code_id = serializers.IntegerField(allow_null=True)
    revenue_account_id = serializers.IntegerField()

    class Meta:
        model = InvoiceLine
        fields = [
            "id",
            "position",
            "item_id",
            "sales_order_line_id",
            "description",
            "quantity",
            "unit_price",
            "discount_type",
            "discount_value",
            "tax_code_id",
            "revenue_account_id",
            "subtotal",
            "line_discount",
            "document_discount",
            "taxable",
            "tax",
            "total",
            "tax_rate",
            "credited_taxable",
            "credited_tax",
        ]


class InvoiceListSerializer(PdfMixin, serializers.ModelSerializer):
    customer_id = serializers.IntegerField()
    customer_name = serializers.CharField(source="customer.name")
    outstanding = serializers.DecimalField(max_digits=24, decimal_places=6, read_only=True)
    is_overdue = serializers.SerializerMethodField()
    project_reference = serializers.CharField(source="project.reference", default=None)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "status",
            "customer_id",
            "customer_name",
            "project_reference",
            "issue_date",
            "due_date",
            "currency",
            "total",
            "amount_paid",
            "amount_credited",
            "outstanding",
            "is_overdue",
            "pdf_status",
            "pdf_url",
            "created_at",
        ]

    def get_is_overdue(self, obj) -> bool:
        return obj.status in ("issued", "partially_paid") and obj.due_date < timezone.localdate()


class InvoiceDetailSerializer(InvoiceListSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    project_id = serializers.IntegerField(allow_null=True)
    milestone_id = serializers.IntegerField(allow_null=True)
    sales_order_id = serializers.IntegerField(allow_null=True)
    journal = serializers.SerializerMethodField()
    void_journal = serializers.SerializerMethodField()
    approval_id = serializers.IntegerField(allow_null=True)
    branding_version = serializers.IntegerField(source="branding_version.number", default=None)
    created_by = serializers.CharField(source="created_by.display_name")
    approved_by = serializers.CharField(source="approved_by.display_name", default=None)
    issued_by = serializers.CharField(source="issued_by.display_name", default=None)
    allocations = serializers.SerializerMethodField()
    credit_notes = serializers.SerializerMethodField()

    class Meta(InvoiceListSerializer.Meta):
        fields = [
            *InvoiceListSerializer.Meta.fields,
            "project_id",
            "milestone_id",
            "sales_order_id",
            "prices_include_tax",
            "discount_type",
            "discount_value",
            "reference",
            "notes",
            "subtotal",
            "line_discount",
            "document_discount",
            "taxable",
            "tax",
            "exchange_rate",
            "base_total",
            "revision",
            "lines",
            "journal",
            "void_journal",
            "void_reason",
            "approval_id",
            "branding_version",
            "snapshot",
            "created_by",
            "approved_by",
            "approved_at",
            "issued_by",
            "issued_at",
            "pdf_error",
            "allocations",
            "credit_notes",
        ]

    def get_journal(self, obj) -> dict | None:
        return journal_ref(obj.journal)

    def get_void_journal(self, obj) -> dict | None:
        return journal_ref(obj.void_journal)

    def get_allocations(self, obj) -> list:
        return [
            {
                "payment_id": a.payment_id,
                "number": a.payment.number,
                "date": a.payment.payment_date,
                "status": a.payment.status,
                "amount": str(a.amount),
            }
            for a in obj.allocations.select_related("payment").order_by(
                "payment__payment_date", "pk"
            )
        ]

    def get_credit_notes(self, obj) -> list:
        return [
            {
                "id": c.pk,
                "number": c.number,
                "status": c.status,
                "total": str(c.total),
                "date": c.issue_date,
            }
            for c in obj.credit_notes.all()
        ]


class InvoiceLineInput(DocumentLineInput):
    sales_order_line_id = serializers.IntegerField(required=False, allow_null=True)
    revenue_account_id = serializers.IntegerField(required=False, allow_null=True)


class InvoiceInput(serializers.Serializer):
    customer_id = serializers.IntegerField(required=False)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    milestone_id = serializers.IntegerField(required=False, allow_null=True)
    sales_order_id = serializers.IntegerField(required=False, allow_null=True)
    issue_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, required=False)
    prices_include_tax = serializers.BooleanField(required=False)
    discount_type = serializers.ChoiceField(choices=DISCOUNT_TYPES, required=False)
    discount_value = DecimalText(required=False)
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    revision = serializers.IntegerField(required=False)
    lines = InvoiceLineInput(many=True, required=False)


class FromSourceInput(serializers.Serializer):
    order_id = serializers.IntegerField(required=False)
    milestone_id = serializers.IntegerField(required=False)
    issue_date = serializers.DateField(required=False)
    tax_code_id = serializers.IntegerField(required=False, allow_null=True)
    revenue_account_id = serializers.IntegerField(required=False, allow_null=True)


class DocumentDecisionInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    date = serializers.DateField(required=False)


class AllocationInput(serializers.Serializer):
    invoice_id = serializers.IntegerField()
    amount = DecimalText()


class PaymentInput(serializers.Serializer):
    customer_id = serializers.IntegerField()
    bank_account_id = serializers.IntegerField()
    payment_date = serializers.DateField(required=False)
    amount = DecimalText()
    method = serializers.ChoiceField(choices=CustomerPayment.METHODS, default="bank_transfer")
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    allocations = AllocationInput(many=True, required=False)
    accept_unapplied = serializers.BooleanField(default=False)


class AllocationSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number")

    class Meta:
        model = PaymentAllocation
        fields = ["invoice_id", "invoice_number", "amount", "base_amount"]


class PaymentSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField()
    customer_name = serializers.CharField(source="customer.name")
    bank_account_id = serializers.IntegerField()
    bank_account_name = serializers.CharField(source="bank_account.name")
    recorded_by = serializers.CharField(source="recorded_by.display_name")
    recorded_by_id = serializers.IntegerField()
    decided_by = serializers.CharField(source="decided_by.display_name", default=None)
    allocations = AllocationSerializer(many=True, read_only=True)
    journal = serializers.SerializerMethodField()
    reversal_journal = serializers.SerializerMethodField()
    receipt = serializers.SerializerMethodField()

    class Meta:
        model = CustomerPayment
        fields = [
            "id",
            "number",
            "status",
            "customer_id",
            "customer_name",
            "bank_account_id",
            "bank_account_name",
            "payment_date",
            "currency",
            "amount",
            "unapplied_amount",
            "method",
            "reference",
            "notes",
            "recorded_by",
            "recorded_by_id",
            "recorded_at",
            "decided_by",
            "decided_at",
            "decision_reason",
            "approval_id",
            "exchange_rate",
            "base_amount",
            "allocations",
            "journal",
            "reversal_journal",
            "receipt",
        ]

    def get_journal(self, obj) -> dict | None:
        return journal_ref(obj.journal)

    def get_reversal_journal(self, obj) -> dict | None:
        return journal_ref(obj.reversal_journal)

    def get_receipt(self, obj) -> dict | None:
        receipt = getattr(obj, "receipt", None)
        if receipt is None:
            return None
        return {"id": receipt.pk, "number": receipt.number, "status": receipt.status}


class ReceiptSerializer(PdfMixin, serializers.ModelSerializer):
    payment_id = serializers.IntegerField()
    payment_number = serializers.CharField(source="payment.number")
    customer_name = serializers.CharField(source="payment.customer.name")
    amount = serializers.DecimalField(source="payment.amount", max_digits=24, decimal_places=6)
    currency = serializers.CharField(source="payment.currency")
    branding_version = serializers.IntegerField(source="branding_version.number")

    class Meta:
        model = MoneyReceipt
        fields = [
            "id",
            "number",
            "status",
            "issue_date",
            "payment_id",
            "payment_number",
            "customer_name",
            "amount",
            "currency",
            "branding_version",
            "snapshot",
            "pdf_status",
            "pdf_url",
            "pdf_error",
        ]


class CreditLineInput(serializers.Serializer):
    invoice_line_id = serializers.IntegerField()
    amount = DecimalText()


class CreditNoteInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500)
    issue_date = serializers.DateField(required=False)
    full = serializers.BooleanField(default=False)
    lines = CreditLineInput(many=True, required=False)


class CreditNoteSerializer(PdfMixin, serializers.ModelSerializer):
    invoice_id = serializers.IntegerField()
    invoice_number = serializers.CharField(source="invoice.number")
    customer_id = serializers.IntegerField()
    customer_name = serializers.CharField(source="customer.name")
    journal = serializers.SerializerMethodField()

    class Meta:
        model = CreditNote
        fields = [
            "id",
            "number",
            "status",
            "invoice_id",
            "invoice_number",
            "customer_id",
            "customer_name",
            "issue_date",
            "reason",
            "currency",
            "taxable",
            "tax",
            "total",
            "applied_amount",
            "credit_amount",
            "approval_id",
            "journal",
            "pdf_status",
            "pdf_url",
            "pdf_error",
        ]

    def get_journal(self, obj) -> dict | None:
        return journal_ref(obj.journal)


class ApplicationInput(serializers.Serializer):
    invoice_id = serializers.IntegerField()
    amount = DecimalText()
    application_date = serializers.DateField(required=False)


class ApplicationSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number")

    class Meta:
        model = CreditApplication
        fields = ["id", "invoice_id", "invoice_number", "application_date", "currency", "amount"]


class RefundInput(serializers.Serializer):
    customer_id = serializers.IntegerField()
    bank_account_id = serializers.IntegerField()
    amount = DecimalText()
    refund_date = serializers.DateField(required=False)
    method = serializers.ChoiceField(choices=CustomerPayment.METHODS, default="bank_transfer")
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    reason = serializers.CharField(max_length=500)


class RefundSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name")
    bank_account_name = serializers.CharField(source="bank_account.name")
    journal = serializers.SerializerMethodField()

    class Meta:
        model = Refund
        fields = [
            "id",
            "number",
            "status",
            "customer_id",
            "customer_name",
            "bank_account_id",
            "bank_account_name",
            "refund_date",
            "currency",
            "amount",
            "method",
            "reference",
            "reason",
            "approval_id",
            "journal",
        ]

    def get_journal(self, obj) -> dict | None:
        return journal_ref(obj.journal)


class ScheduleSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField()
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    project_id = serializers.IntegerField(allow_null=True, required=False)
    auto_issue_authorized_by = serializers.CharField(
        source="auto_issue_authorized_by.display_name", default=None, read_only=True
    )

    class Meta:
        model = RecurringInvoiceSchedule
        fields = [
            "id",
            "name",
            "customer_id",
            "customer_name",
            "project_id",
            "currency",
            "frequency",
            "interval",
            "start_date",
            "end_date",
            "next_run_date",
            "due_days",
            "template",
            "auto_issue",
            "auto_issue_authorized_by",
            "status",
            "revision",
            "created_at",
        ]
        read_only_fields = ["next_run_date", "status", "revision", "created_at", "template"]


class ScheduleInput(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False)
    customer_id = serializers.IntegerField(required=False)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, required=False)
    frequency = serializers.ChoiceField(
        choices=RecurringInvoiceSchedule.Frequency.choices, required=False
    )
    interval = serializers.IntegerField(min_value=1, max_value=24, required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False, allow_null=True)
    due_days = serializers.IntegerField(min_value=0, max_value=365, required=False)
    auto_issue = serializers.BooleanField(required=False)
    prices_include_tax = serializers.BooleanField(required=False)
    discount_type = serializers.ChoiceField(choices=DISCOUNT_TYPES, required=False)
    discount_value = DecimalText(required=False)
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    lines = DocumentLineInput(many=True, required=False)


class RunSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", default=None)

    class Meta:
        model = RecurringInvoiceRun
        fields = [
            "id",
            "occurrence_date",
            "status",
            "message",
            "invoice_id",
            "invoice_number",
            "created_at",
        ]


class RunInput(serializers.Serializer):
    until = serializers.DateField(required=False)
    schedule_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class LedgerSettingsSerializer(serializers.ModelSerializer):
    default_revenue_account_id = serializers.IntegerField(allow_null=True, required=False)
    default_expense_account_id = serializers.IntegerField(allow_null=True, required=False)

    class Meta:
        model = LedgerSettings
        fields = ["default_revenue_account_id", "default_expense_account_id", "updated_at"]
        read_only_fields = ["updated_at"]


class StatusInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=["active", "paused", "cancelled"])
