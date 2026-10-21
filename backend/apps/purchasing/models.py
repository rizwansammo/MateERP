"""Payables: vendors, vendor bills, expenses, recurring expenses and vendor payments.

Bills and accrued expenses credit the ``payable`` control account; vendor payments
settle them. An expense paid immediately credits the bank directly and never touches
payables, so a cost is recorded exactly once.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.accounting.models import amount as money_field
from apps.accounting.models import rate
from apps.sales.models import percent, quantity

# These classes remain in the purchasing app; split for readability only.
from .procurement_models import (  # noqa: F401
    GoodsReceipt,
    ProcurementEvidence,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderSnapshot,
    ReceiptBillMatch,
    ReceiptCostCorrection,
    SupplierReturn,
)

USER = settings.AUTH_USER_MODEL
DISCOUNT_TYPES = [("percent", "Percent"), ("fixed", "Fixed")]
METHODS = [
    ("bank_transfer", "Bank transfer"),
    ("cash", "Cash"),
    ("cheque", "Cheque"),
    ("card", "Card"),
    ("mobile_wallet", "Mobile wallet"),
    ("other", "Other"),
]


class Vendor(models.Model):
    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=500, blank=True)
    country = models.CharField(max_length=80, blank=True)
    currency = models.CharField(max_length=3)
    payment_terms_days = models.PositiveSmallIntegerField(default=15)
    tax_id = models.CharField(max_length=60, blank=True)
    website = models.CharField(max_length=200, blank=True)
    default_account = models.ForeignKey(
        "accounting.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    notes = models.CharField(max_length=1000, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(payment_terms_days__lte=365), name="vendor_terms_range"
            )
        ]

    def __str__(self):
        return self.name


class VendorBill(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
        POSTED = "posted", "Posted"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        VOID = "void", "Void"
        CANCELLED = "cancelled", "Cancelled draft"

    POSTED_STATES = ("posted", "partially_paid", "paid")

    number = models.CharField(max_length=80, null=True, blank=True, unique=True)  # noqa: DJ001
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="bills")
    vendor_reference = models.CharField(max_length=80)
    normalized_reference = models.CharField(max_length=80, editable=False)
    project = models.ForeignKey(
        "sales.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    bill_date = models.DateField()
    due_date = models.DateField()
    currency = models.CharField(max_length=3)
    prices_include_tax = models.BooleanField(default=False)
    notes = models.CharField(max_length=1000, blank=True)
    subtotal = money_field(default=0)
    line_discount = money_field(default=0)
    taxable = money_field(default=0)
    tax = money_field(default=0)
    total = money_field(default=0)
    exchange_rate = rate(null=True, blank=True)
    base_total = money_field(null=True, blank=True)
    amount_paid = money_field(default=0)
    base_settled = money_field(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    approval = models.ForeignKey(
        "approvals.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    posted_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    void_journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    void_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-bill_date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "normalized_reference"],
                condition=~Q(status__in=["void", "cancelled"]),
                name="vendor_invoice_once",
            ),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0, total__gte=0, amount_paid__lte=F("total")),
                name="bill_not_overpaid",
            ),
            models.CheckConstraint(
                condition=Q(base_settled__gte=0)
                & (Q(base_total__isnull=True) | Q(base_settled__lte=F("base_total"))),
                name="bill_base_not_oversettled",
            ),
            models.CheckConstraint(
                condition=Q(due_date__gte=F("bill_date")), name="bill_due_after_date"
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["posted", "partially_paid", "paid", "void"])
                | Q(number__isnull=False, journal__isnull=False, base_total__isnull=False),
                name="bill_posted_metadata",
            ),
        ]

    def __str__(self):
        return self.number or f"Draft bill {self.pk}"

    @property
    def outstanding(self):
        return self.total - self.amount_paid


class VendorBillLine(models.Model):
    bill = models.ForeignKey(VendorBill, on_delete=models.PROTECT, related_name="lines")
    position = models.PositiveSmallIntegerField()
    description = models.CharField(max_length=500)
    quantity = quantity()
    unit_price = money_field()
    discount_type = models.CharField(max_length=8, choices=DISCOUNT_TYPES, default="percent")
    discount_value = money_field(default=0)
    tax_code = models.ForeignKey(
        "accounting.TaxCode", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    account = models.ForeignKey("accounting.Account", on_delete=models.PROTECT, related_name="+")
    subtotal = money_field(default=0)
    line_discount = money_field(default=0)
    taxable = money_field(default=0)
    tax = money_field(default=0)
    total = money_field(default=0)
    tax_rate = percent(default=0)
    tax_revision = models.ForeignKey(
        "accounting.TaxRevision", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["bill", "position"]
        constraints = [
            models.UniqueConstraint(fields=["bill", "position"], name="bill_line_position"),
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_price__gte=0, total__gte=0),
                name="bill_line_amounts_valid",
            ),
        ]

    def __str__(self):
        return f"{self.bill_id}:{self.position}"


class Expense(models.Model):
    class Mode(models.TextChoices):
        FOUNDER = "founder", "Paid personally by a founder"
        PAID = "paid", "Paid now from a bank or cash account"
        ACCRUED = "accrued", "Accrued — payable to the vendor"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
        POSTED = "posted", "Posted"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        VOID = "void", "Void"
        CANCELLED = "cancelled", "Cancelled draft"

    number = models.CharField(max_length=80, null=True, blank=True, unique=True)  # noqa: DJ001
    vendor = models.ForeignKey(
        Vendor, null=True, blank=True, on_delete=models.PROTECT, related_name="expenses"
    )
    project = models.ForeignKey(
        "sales.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    expense_date = models.DateField()
    original_transaction_date = models.DateField(null=True, blank=True)
    recognition_reason = models.CharField(max_length=1000, blank=True)
    due_date = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=300)
    currency = models.CharField(max_length=3)
    account = models.ForeignKey("accounting.Account", on_delete=models.PROTECT, related_name="+")
    entered_amount = money_field()
    prices_include_tax = models.BooleanField(default=False)
    tax_code = models.ForeignKey(
        "accounting.TaxCode", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    taxable = money_field(default=0)
    tax = money_field(default=0)
    total = money_field(default=0)
    tax_revision = models.ForeignKey(
        "accounting.TaxRevision", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    payment_mode = models.CharField(max_length=8, choices=Mode.choices)
    bank_account = models.ForeignKey(
        "banking.BankAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    method = models.CharField(max_length=16, choices=METHODS, default="bank_transfer")
    reference = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=1000, blank=True)
    exchange_rate = rate(null=True, blank=True)
    base_total = money_field(null=True, blank=True)
    amount_paid = money_field(default=0)
    base_settled = money_field(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    approval = models.ForeignKey(
        "approvals.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    posted_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    void_journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    void_reason = models.CharField(max_length=500, blank=True)
    recurring_schedule = models.ForeignKey(
        "purchasing.RecurringExpenseSchedule",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expenses",
    )

    class Meta:
        ordering = ["-expense_date", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(payment_mode="paid", bank_account__isnull=False))
                | Q(payment_mode="accrued", vendor__isnull=False, due_date__isnull=False)
                | Q(payment_mode="founder", bank_account__isnull=True),
                name="expense_mode_consistent",
            ),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0, total__gte=0, amount_paid__lte=F("total"))
                & (Q(payment_mode="accrued") | Q(amount_paid=0)),
                name="expense_not_overpaid",
            ),
            models.CheckConstraint(
                condition=Q(base_settled__gte=0)
                & (Q(base_total__isnull=True) | Q(base_settled__lte=F("base_total"))),
                name="expense_base_not_oversettled",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["posted", "partially_paid", "paid", "void"])
                | Q(number__isnull=False, journal__isnull=False, base_total__isnull=False),
                name="expense_posted_metadata",
            ),
        ]

    def __str__(self):
        return self.number or f"Draft expense {self.pk}"

    @property
    def outstanding(self):
        return self.total - self.amount_paid if self.payment_mode == "accrued" else 0


class RecurringExpenseSchedule(models.Model):
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
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="recurring")
    currency = models.CharField(max_length=3)
    frequency = models.CharField(max_length=10, choices=Frequency.choices)
    interval = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    next_run_date = models.DateField(null=True, blank=True)
    reminder_days = models.PositiveSmallIntegerField(default=7)
    template = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(interval__gte=1, interval__lte=24, reminder_days__lte=90),
                name="recurring_expense_range",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="recurring_expense_dates",
            ),
        ]

    def __str__(self):
        return self.name


class RecurringExpenseRun(models.Model):
    schedule = models.ForeignKey(
        RecurringExpenseSchedule, on_delete=models.PROTECT, related_name="runs"
    )
    occurrence_date = models.DateField()
    expense = models.OneToOneField(
        Expense, null=True, blank=True, on_delete=models.PROTECT, related_name="recurring_run"
    )
    status = models.CharField(
        max_length=10, choices=[("drafted", "Draft created"), ("failed", "Failed")]
    )
    message = models.CharField(max_length=500, blank=True)
    run_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurrence_date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "occurrence_date"], name="recurring_expense_occurrence_once"
            )
        ]

    def __str__(self):
        return f"{self.schedule_id}@{self.occurrence_date}"


class VendorPayment(models.Model):
    class Status(models.TextChoices):
        AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
        PAID = "paid", "Paid & posted"
        REJECTED = "rejected", "Rejected"
        REVERSED = "reversed", "Reversed"

    number = models.CharField(max_length=80, unique=True)
    client_key = models.CharField(max_length=160, unique=True)
    fingerprint = models.CharField(max_length=64)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="payments")
    bank_account = models.ForeignKey(
        "banking.BankAccount", on_delete=models.PROTECT, related_name="+"
    )
    payment_date = models.DateField()
    currency = models.CharField(max_length=3)
    amount = money_field()
    base_amount = money_field(null=True, blank=True)
    method = models.CharField(max_length=16, choices=METHODS, default="bank_transfer")
    reference = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=1000, blank=True)
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
    reversal_journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-payment_date", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="vendor_payment_positive"),
            models.CheckConstraint(
                condition=~Q(status__in=["paid", "reversed"])
                | Q(journal__isnull=False, base_amount__isnull=False),
                name="vendor_payment_posted_metadata",
            ),
        ]

    def __str__(self):
        return self.number


class VendorPaymentAllocation(models.Model):
    payment = models.ForeignKey(VendorPayment, on_delete=models.PROTECT, related_name="allocations")
    bill = models.ForeignKey(
        VendorBill, null=True, blank=True, on_delete=models.PROTECT, related_name="allocations"
    )
    expense = models.ForeignKey(
        Expense, null=True, blank=True, on_delete=models.PROTECT, related_name="allocations"
    )
    amount = money_field()
    base_amount = money_field(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0)
                & (
                    Q(bill__isnull=False, expense__isnull=True)
                    | Q(bill__isnull=True, expense__isnull=False)
                ),
                name="vendor_allocation_one_target",
            ),
            models.UniqueConstraint(
                fields=["payment", "bill"],
                condition=Q(bill__isnull=False),
                name="vendor_alloc_bill_once",
            ),
            models.UniqueConstraint(
                fields=["payment", "expense"],
                condition=Q(expense__isnull=False),
                name="vendor_alloc_expense_once",
            ),
        ]

    def __str__(self):
        return f"{self.payment_id}"
