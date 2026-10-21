"""One authoritative ledger. Amounts are native currency; base amounts are snapshots."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


def amount(**kwargs):
    return models.DecimalField(max_digits=24, decimal_places=6, **kwargs)


def rate(**kwargs):
    return models.DecimalField(max_digits=30, decimal_places=12, **kwargs)


class Account(models.Model):
    class Type(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        REVENUE = "revenue", "Revenue"
        EXPENSE = "expense", "Expense"

    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=160)
    account_type = models.CharField(max_length=12, choices=Type.choices)
    subtype = models.CharField(max_length=80, blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    normal_side = models.CharField(max_length=6, choices=[("debit", "Debit"), ("credit", "Credit")])
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    is_postable = models.BooleanField(default=True)
    currency = models.CharField(max_length=3, blank=True)
    control = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["control"], condition=~Q(control=""), name="unique_control_account"
            ),
            models.CheckConstraint(
                condition=~Q(parent=models.F("pk")), name="account_not_own_parent"
            ),
        ]

    def __str__(self):
        return f"{self.code} · {self.name}"


class FiscalYear(models.Model):
    name = models.CharField(max_length=80)
    start = models.DateField(unique=True)
    end = models.DateField()
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start"]
        constraints = [
            models.CheckConstraint(condition=Q(end__gte=models.F("start")), name="year_dates_valid")
        ]

    def __str__(self):
        return self.name


class AccountingPeriod(models.Model):
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, related_name="periods")
    start = models.DateField(unique=True)
    end = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    closed_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["start"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end__gte=models.F("start")), name="period_dates_valid"
            )
        ]

    def __str__(self):
        return str(self.start)[:7]


class ExchangeRate(models.Model):
    currency = models.CharField(max_length=3)
    base_currency = models.CharField(max_length=3)
    effective_date = models.DateField()
    value = rate()
    source = models.CharField(max_length=200)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-pk"]
        constraints = [models.CheckConstraint(condition=Q(value__gt=0), name="fx_positive")]
        indexes = [models.Index(fields=["currency", "base_currency", "effective_date"])]

    def __str__(self):
        return f"{self.currency}/{self.base_currency} {self.effective_date}"


class TaxCode(models.Model):
    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class TaxRevision(models.Model):
    tax_code = models.ForeignKey(TaxCode, on_delete=models.PROTECT, related_name="revisions")
    effective_date = models.DateField()
    percent = models.DecimalField(max_digits=9, decimal_places=6)
    input_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="input_tax_revisions"
    )
    output_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="output_tax_revisions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(percent__gte=0, percent__lte=100), name="tax_percent_valid"
            )
        ]

    def __str__(self):
        return f"{self.tax_code_id} {self.percent}%"


class JournalEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=80, null=True, unique=True)  # noqa: DJ001 -- unnumbered drafts
    journal_date = models.DateField()
    posting_date = models.DateField()
    description = models.CharField(max_length=500)
    status = models.CharField(
        max_length=12,
        choices=[("draft", "Draft"), ("pending", "Awaiting approval"), ("posted", "Posted")],
        default="draft",
    )
    kind = models.CharField(max_length=24, default="manual")
    source_type = models.CharField(max_length=60, default="manual")
    source_id = models.CharField(max_length=100)
    source_action = models.CharField(max_length=40, default="post")
    base_currency = models.CharField(max_length=3)
    period = models.ForeignKey(AccountingPeriod, null=True, on_delete=models.PROTECT)
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by"
    )
    adjustment_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="adjustments"
    )
    reason = models.CharField(max_length=500, blank=True)
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_journals"
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.PROTECT,
        related_name="posted_journals",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True)
    approval = models.ForeignKey(
        "approvals.ApprovalRequest", null=True, on_delete=models.PROTECT, related_name="journals"
    )

    class Meta:
        ordering = ["-posting_date", "-created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_type", "source_id", "source_action"], name="journal_source_identity"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "pending", "posted"]), name="journal_status_valid"
            ),
            models.CheckConstraint(
                condition=~Q(status="posted")
                | Q(
                    number__isnull=False,
                    period__isnull=False,
                    posted_by__isnull=False,
                    posted_at__isnull=False,
                ),
                name="posted_metadata_present",
            ),
        ]

    def __str__(self):
        return self.number or f"Draft {self.pk}"


class JournalLine(models.Model):
    journal = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    position = models.PositiveIntegerField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="journal_lines")
    description = models.CharField(max_length=300, blank=True)
    currency = models.CharField(max_length=3)
    debit = amount(default=0)
    credit = amount(default=0)
    exchange_rate = rate(default=1)
    rate_source = models.CharField(max_length=200, blank=True)
    base_debit = amount(default=0)
    base_credit = amount(default=0)
    valuation = models.CharField(max_length=20, default="spot")
    account_snapshot = models.JSONField(default=dict)
    dimensions = models.JSONField(default=dict)
    tax_revision = models.ForeignKey(TaxRevision, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["journal", "position"], name="journal_line_position"),
            models.CheckConstraint(
                condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)),
                name="line_one_positive_side",
            ),
            models.CheckConstraint(
                condition=Q(base_debit__gte=0, base_credit__gte=0, exchange_rate__gt=0),
                name="line_base_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.journal_id}:{self.position}"


class PostingIdentity(models.Model):
    key = models.CharField(max_length=160, unique=True)
    fingerprint = models.CharField(max_length=64)
    journal = models.ForeignKey(JournalEntry, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.key


class JournalSequence(models.Model):
    year = models.PositiveIntegerField(unique=True)
    last_value = models.PositiveBigIntegerField(default=0)

    def __str__(self):
        return str(self.year)


# Import after amount()/journal classes to avoid circular model construction.
from .onboarding_models import HistoricalRecord, HistoricalTreatment  # noqa: E402, F401
