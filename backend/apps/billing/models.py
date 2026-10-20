"""Receivables: invoices, payments, receipts, credit notes, refunds and recurring billing.

Every financial effect is a journal posted through a registered domain adapter; these
records hold the business documents, their frozen snapshots and the journal links.
Running totals (paid, credited, settled base) are maintained under row locks and
guarded by check constraints, so a document can never be over-settled.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.accounting.models import amount as money_field
from apps.accounting.models import rate
from apps.sales.models import percent, quantity

USER = settings.AUTH_USER_MODEL
DISCOUNT_TYPES = [("percent", "Percent"), ("fixed", "Fixed")]
PDF_STATUSES = [
    ("none", "Not generated"),
    ("pending", "Generating"),
    ("ready", "Ready"),
    ("failed", "Failed"),
]


class LedgerSettings(models.Model):
    """Singleton default revenue/expense accounts for commercial documents."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    default_revenue_account = models.ForeignKey(
        "accounting.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    default_expense_account = models.ForeignKey(
        "accounting.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(USER, null=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="ledger_settings_singleton")]

    def __str__(self):
        return "Ledger settings"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Awaiting approval"
        APPROVED = "approved", "Approved"
        ISSUED = "issued", "Issued"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        CREDITED = "credited", "Credited"
        VOID = "void", "Void"
        CANCELLED = "cancelled", "Cancelled draft"

    ISSUED_STATES = ("issued", "partially_paid", "paid", "credited")

    number = models.CharField(max_length=80, null=True, blank=True, unique=True)  # noqa: DJ001
    customer = models.ForeignKey(
        "sales.Customer", on_delete=models.PROTECT, related_name="invoices"
    )
    project = models.ForeignKey(
        "sales.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="invoices"
    )
    milestone = models.ForeignKey(
        "sales.Milestone", null=True, blank=True, on_delete=models.PROTECT, related_name="invoices"
    )
    sales_order = models.ForeignKey(
        "sales.SalesOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="invoices"
    )
    issue_date = models.DateField()
    due_date = models.DateField()
    currency = models.CharField(max_length=3)
    prices_include_tax = models.BooleanField(default=False)
    discount_type = models.CharField(max_length=8, choices=DISCOUNT_TYPES, default="percent")
    discount_value = money_field(default=0)
    reference = models.CharField(max_length=80, blank=True)
    notes = models.CharField(max_length=2000, blank=True)
    subtotal = money_field(default=0)
    line_discount = money_field(default=0)
    document_discount = money_field(default=0)
    taxable = money_field(default=0)
    tax = money_field(default=0)
    total = money_field(default=0)
    exchange_rate = rate(null=True, blank=True)
    base_total = money_field(null=True, blank=True)
    amount_paid = money_field(default=0)
    amount_credited = money_field(default=0)
    base_settled = money_field(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval = models.ForeignKey(
        "approvals.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    issued_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=500, blank=True)
    journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    void_journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    branding_version = models.ForeignKey(
        "branding.BrandingVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    snapshot = models.JSONField(default=dict, blank=True)
    recurring_schedule = models.ForeignKey(
        "billing.RecurringInvoiceSchedule",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    pdf_status = models.CharField(max_length=8, choices=PDF_STATUSES, default="none")
    pdf_file = models.OneToOneField(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    pdf_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-issue_date", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0, amount_credited__gte=0, total__gte=0)
                & Q(amount_paid__lte=F("total") - F("amount_credited")),
                name="invoice_not_oversettled",
            ),
            models.CheckConstraint(
                condition=Q(base_settled__gte=0)
                & (Q(base_total__isnull=True) | Q(base_settled__lte=F("base_total"))),
                name="invoice_base_not_oversettled",
            ),
            models.CheckConstraint(
                condition=Q(due_date__gte=F("issue_date")), name="invoice_due_after_issue"
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["issued", "partially_paid", "paid", "credited", "void"])
                | Q(
                    number__isnull=False,
                    journal__isnull=False,
                    branding_version__isnull=False,
                    issued_at__isnull=False,
                    exchange_rate__isnull=False,
                    base_total__isnull=False,
                ),
                name="invoice_issued_metadata",
            ),
            models.UniqueConstraint(
                fields=["milestone"],
                condition=Q(milestone__isnull=False) & ~Q(status__in=["void", "cancelled"]),
                name="milestone_invoiced_once",
            ),
        ]
        indexes = [models.Index(fields=["customer", "status"]), models.Index(fields=["due_date"])]

    def __str__(self):
        return self.number or f"Draft invoice {self.pk}"

    @property
    def outstanding(self):
        return self.total - self.amount_paid - self.amount_credited


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="lines")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(
        "sales.BillingItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    sales_order_line = models.ForeignKey(
        "sales.SalesOrderLine",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="invoice_lines",
    )
    description = models.CharField(max_length=500)
    quantity = quantity()
    unit_price = money_field()
    discount_type = models.CharField(max_length=8, choices=DISCOUNT_TYPES, default="percent")
    discount_value = money_field(default=0)
    tax_code = models.ForeignKey(
        "accounting.TaxCode", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    revenue_account = models.ForeignKey(
        "accounting.Account", on_delete=models.PROTECT, related_name="+"
    )
    subtotal = money_field(default=0)
    line_discount = money_field(default=0)
    document_discount = money_field(default=0)
    taxable = money_field(default=0)
    tax = money_field(default=0)
    total = money_field(default=0)
    tax_rate = percent(default=0)
    tax_revision = models.ForeignKey(
        "accounting.TaxRevision", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    credited_taxable = money_field(default=0)
    credited_tax = money_field(default=0)

    class Meta:
        ordering = ["invoice", "position"]
        constraints = [
            models.UniqueConstraint(fields=["invoice", "position"], name="invoice_line_position"),
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_price__gte=0, total__gte=0),
                name="invoice_line_amounts_valid",
            ),
            models.CheckConstraint(
                condition=Q(credited_taxable__gte=0, credited_tax__gte=0)
                & Q(credited_taxable__lte=F("taxable"), credited_tax__lte=F("tax")),
                name="invoice_line_not_overcredited",
            ),
        ]

    def __str__(self):
        return f"{self.invoice_id}:{self.position}"


class CustomerPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending_verification", "Pending verification"
        AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
        VERIFIED = "verified", "Verified & posted"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        REVERSED = "reversed", "Reversed"

    METHODS = [
        ("bank_transfer", "Bank transfer"),
        ("cash", "Cash"),
        ("cheque", "Cheque"),
        ("card", "Card"),
        ("mobile_wallet", "Mobile wallet"),
        ("other", "Other"),
    ]

    number = models.CharField(max_length=80, unique=True)
    client_key = models.CharField(max_length=160, null=True, blank=True, unique=True)  # noqa: DJ001
    fingerprint = models.CharField(max_length=64, blank=True)
    customer = models.ForeignKey(
        "sales.Customer", on_delete=models.PROTECT, related_name="payments"
    )
    bank_account = models.ForeignKey(
        "banking.BankAccount", on_delete=models.PROTECT, related_name="customer_payments"
    )
    payment_date = models.DateField()
    currency = models.CharField(max_length=3)
    amount = money_field()
    unapplied_amount = money_field(default=0)
    method = models.CharField(max_length=16, choices=METHODS, default="bank_transfer")
    reference = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    recorded_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    recorded_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.CharField(max_length=500, blank=True)
    approval = models.ForeignKey(
        "approvals.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    exchange_rate = rate(null=True, blank=True)
    base_amount = money_field(null=True, blank=True)
    journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reversal_journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-payment_date", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0, unapplied_amount__gte=0)
                & Q(unapplied_amount__lte=F("amount")),
                name="payment_amounts_valid",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["verified", "reversed"])
                | Q(journal__isnull=False, base_amount__isnull=False),
                name="payment_posted_metadata",
            ),
        ]

    def __str__(self):
        return self.number


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(
        CustomerPayment, on_delete=models.PROTECT, related_name="allocations"
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="allocations")
    amount = money_field()
    base_amount = money_field(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["payment", "invoice"], name="allocation_once"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="allocation_positive"),
        ]

    def __str__(self):
        return f"{self.payment_id}→{self.invoice_id}"


class MoneyReceipt(models.Model):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        CANCELLED = "cancelled", "Cancelled (payment reversed)"

    number = models.CharField(max_length=80, unique=True)
    payment = models.OneToOneField(
        CustomerPayment, on_delete=models.PROTECT, related_name="receipt"
    )
    issue_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ISSUED)
    branding_version = models.ForeignKey(
        "branding.BrandingVersion", on_delete=models.PROTECT, related_name="+"
    )
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    pdf_status = models.CharField(max_length=8, choices=PDF_STATUSES, default="none")
    pdf_file = models.OneToOneField(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    pdf_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-issue_date", "-pk"]

    def __str__(self):
        return self.number


class CreditNote(models.Model):
    class Status(models.TextChoices):
        AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
        ISSUED = "issued", "Issued"
        REJECTED = "rejected", "Rejected"

    number = models.CharField(max_length=80, null=True, blank=True, unique=True)  # noqa: DJ001
    client_key = models.CharField(max_length=160, null=True, blank=True, unique=True)  # noqa: DJ001
    fingerprint = models.CharField(max_length=64, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="credit_notes")
    customer = models.ForeignKey("sales.Customer", on_delete=models.PROTECT, related_name="+")
    issue_date = models.DateField()
    reason = models.CharField(max_length=500)
    currency = models.CharField(max_length=3)
    taxable = money_field(default=0)
    tax = money_field(default=0)
    total = money_field(default=0)
    applied_amount = money_field(default=0)
    credit_amount = money_field(default=0)
    base_total = money_field(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    approval = models.ForeignKey(
        "approvals.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    branding_version = models.ForeignKey(
        "branding.BrandingVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    snapshot = models.JSONField(default=dict, blank=True)
    pdf_status = models.CharField(max_length=8, choices=PDF_STATUSES, default="none")
    pdf_file = models.OneToOneField(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    pdf_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-issue_date", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(total__gt=0, applied_amount__gte=0, credit_amount__gte=0)
                & Q(total=F("applied_amount") + F("credit_amount")),
                name="credit_note_split_exact",
            ),
            models.CheckConstraint(
                condition=~Q(status="issued")
                | Q(number__isnull=False, journal__isnull=False, base_total__isnull=False),
                name="credit_note_issued_metadata",
            ),
        ]

    def __str__(self):
        return self.number or f"Credit note request {self.pk}"


class CreditNoteLine(models.Model):
    credit_note = models.ForeignKey(CreditNote, on_delete=models.PROTECT, related_name="lines")
    invoice_line = models.ForeignKey(InvoiceLine, on_delete=models.PROTECT, related_name="credits")
    taxable = money_field()
    tax = money_field(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(taxable__gte=0, tax__gte=0) & (Q(taxable__gt=0) | Q(tax__gt=0)),
                name="credit_line_positive",
            )
        ]

    def __str__(self):
        return f"{self.credit_note_id}:{self.invoice_line_id}"


class CustomerCreditMovement(models.Model):
    """Customer-credit subledger detail (unapplied receipts, excess credits, uses).

    Signed native and base amounts; the per-customer, per-currency sum reconciles to
    the ``customer_credit`` control account. It is subledger detail, not a ledger.
    """

    customer = models.ForeignKey("sales.Customer", on_delete=models.PROTECT, related_name="+")
    currency = models.CharField(max_length=3)
    amount = money_field()
    base_amount = money_field()
    kind = models.CharField(
        max_length=20,
        choices=[
            ("unapplied", "Unapplied payment"),
            ("credit_note", "Excess credit note"),
            ("application", "Applied to invoice"),
            ("refund", "Refunded"),
            ("reversal", "Payment reversed"),
        ],
    )
    payment = models.ForeignKey(
        CustomerPayment, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    credit_note = models.ForeignKey(
        CreditNote, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    application = models.ForeignKey(
        "billing.CreditApplication",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    refund = models.ForeignKey(
        "billing.Refund", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["customer", "currency"])]
        constraints = [
            models.CheckConstraint(
                condition=~Q(amount=0)
                & (Q(amount__gt=0, base_amount__gte=0) | Q(amount__lt=0, base_amount__lte=0)),
                name="credit_movement_signs",
            )
        ]

    def __str__(self):
        return f"{self.customer_id} {self.amount} {self.currency}"


class CreditApplication(models.Model):
    customer = models.ForeignKey("sales.Customer", on_delete=models.PROTECT, related_name="+")
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="credit_applications"
    )
    application_date = models.DateField()
    currency = models.CharField(max_length=3)
    amount = money_field()
    base_amount = money_field()
    client_key = models.CharField(max_length=160, unique=True)
    fingerprint = models.CharField(max_length=64, blank=True)
    journal = models.OneToOneField(
        "accounting.JournalEntry", on_delete=models.PROTECT, related_name="+"
    )
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="application_positive")
        ]

    def __str__(self):
        return f"{self.invoice_id} {self.amount}"


class Refund(models.Model):
    class Status(models.TextChoices):
        AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
        PAID = "paid", "Paid"
        REJECTED = "rejected", "Rejected"

    number = models.CharField(max_length=80, unique=True)
    client_key = models.CharField(max_length=160, unique=True)
    fingerprint = models.CharField(max_length=64, blank=True)
    customer = models.ForeignKey("sales.Customer", on_delete=models.PROTECT, related_name="refunds")
    bank_account = models.ForeignKey(
        "banking.BankAccount", on_delete=models.PROTECT, related_name="+"
    )
    refund_date = models.DateField()
    currency = models.CharField(max_length=3)
    amount = money_field()
    base_amount = money_field(null=True, blank=True)
    method = models.CharField(
        max_length=16, choices=CustomerPayment.METHODS, default="bank_transfer"
    )
    reference = models.CharField(max_length=120, blank=True)
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=Status.choices)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    approval = models.ForeignKey(
        "approvals.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-refund_date", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="refund_positive"),
            models.CheckConstraint(
                condition=~Q(status="paid") | Q(journal__isnull=False, base_amount__isnull=False),
                name="refund_paid_metadata",
            ),
        ]

    def __str__(self):
        return self.number


class RecurringInvoiceSchedule(models.Model):
    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        YEARLY = "yearly", "Yearly"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    name = models.CharField(max_length=160)
    customer = models.ForeignKey("sales.Customer", on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey(
        "sales.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    currency = models.CharField(max_length=3)
    frequency = models.CharField(max_length=10, choices=Frequency.choices)
    interval = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    next_run_date = models.DateField(null=True, blank=True)
    due_days = models.PositiveSmallIntegerField(default=30)
    template = models.JSONField(default=dict)
    auto_issue = models.BooleanField(default=False)
    auto_issue_authorized_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(interval__gte=1, interval__lte=24, due_days__lte=365),
                name="recurring_invoice_range",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="recurring_invoice_dates",
            ),
            models.CheckConstraint(
                condition=Q(auto_issue=False) | Q(auto_issue_authorized_by__isnull=False),
                name="recurring_invoice_auto_issue_owner",
            ),
        ]

    def __str__(self):
        return self.name


class RecurringInvoiceRun(models.Model):
    class Status(models.TextChoices):
        DRAFTED = "drafted", "Draft created"
        ISSUED = "issued", "Issued"
        FAILED = "failed", "Failed"

    schedule = models.ForeignKey(
        RecurringInvoiceSchedule, on_delete=models.PROTECT, related_name="runs"
    )
    occurrence_date = models.DateField()
    invoice = models.OneToOneField(
        Invoice, null=True, blank=True, on_delete=models.PROTECT, related_name="recurring_run"
    )
    status = models.CharField(max_length=10, choices=Status.choices)
    message = models.CharField(max_length=500, blank=True)
    run_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurrence_date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "occurrence_date"], name="recurring_invoice_occurrence_once"
            )
        ]

    def __str__(self):
        return f"{self.schedule_id}@{self.occurrence_date}"
