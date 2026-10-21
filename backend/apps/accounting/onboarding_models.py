"""Historical provenance and reviewed cutover claims, not a second expense ledger."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from .models import amount


class HistoricalRecord(models.Model):
    external_reference = models.CharField(max_length=120, unique=True)
    original_date = models.DateField()
    description = models.CharField(max_length=500)
    currency = models.CharField(max_length=3)
    amount = amount()
    payment_source = models.CharField(max_length=200)
    funding_classification = models.CharField(
        max_length=24,
        choices=[
            ("company_expense", "Company-paid expense"),
            ("founder_expense", "Founder-paid expense"),
            ("contribution", "Contribution"),
            ("loan", "Loan"),
            ("reimbursement", "Reimbursement"),
            ("personal_settlement", "Personal settlement"),
            ("bank_balance", "Prior bank balance"),
            ("vendor_payable", "Outstanding vendor obligation"),
            ("inventory_opening", "Prior inventory balance"),
        ],
    )
    pre_registration = models.BooleanField(default=False)
    party = models.ForeignKey(
        "company.FinancialParty", null=True, blank=True, on_delete=models.PROTECT
    )
    evidence = models.ForeignKey(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT
    )
    notes = models.CharField(max_length=2000, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-original_date", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="historical_record_positive")
        ]

    def __str__(self):
        return self.external_reference


class HistoricalTreatment(models.Model):
    """One authorized disposition per provenance record prevents opening + reposting."""

    record = models.ForeignKey(
        HistoricalRecord, on_delete=models.PROTECT, related_name="treatments"
    )
    mode = models.CharField(
        max_length=16,
        choices=[
            ("reconstructed", "Reconstructed transaction"),
            ("opening_only", "Opening-only balance"),
            ("linked", "Link independently verified existing source"),
        ],
    )
    recognition_date = models.DateField()
    reason = models.CharField(max_length=2000)
    payload = models.JSONField(default=dict)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    approval = models.ForeignKey(
        "approvals.ApprovalRequest", null=True, blank=True, on_delete=models.PROTECT
    )
    status = models.CharField(
        max_length=16,
        default="pending",
        choices=[
            ("pending", "Pending independent review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
    )
    journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT
    )
    expense = models.OneToOneField(
        "purchasing.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="historical_treatment",
    )
    founder_transaction = models.OneToOneField(
        "founders.CorporateTransaction",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="historical_treatment",
    )
    vendor_bill = models.OneToOneField(
        "purchasing.VendorBill",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="historical_treatment",
    )
    personal_settlement = models.OneToOneField(
        "founders.PersonalSettlement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="historical_treatment",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["record"],
                condition=Q(status__in=("pending", "approved")),
                name="one_historical_disposition",
            )
        ]

    def __str__(self):
        return f"{self.record_id}:{self.mode}"
