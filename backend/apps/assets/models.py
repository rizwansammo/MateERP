import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounting.models import amount


class Asset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tag = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=80)
    description = models.CharField(max_length=1000, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=200, blank=True)
    custodian_reference = models.CharField(max_length=200, blank=True)
    source_line = models.ForeignKey(
        "accounting.JournalLine", on_delete=models.PROTECT, related_name="capitalizations"
    )
    source_snapshot = models.JSONField()
    acquisition_date = models.DateField()
    recognition_date = models.DateField()
    in_service_date = models.DateField()
    cost = amount()
    journal = models.OneToOneField(
        "accounting.JournalEntry", on_delete=models.PROTECT, related_name="+"
    )
    depreciation_account = models.ForeignKey(
        "accounting.Account", on_delete=models.PROTECT, related_name="+"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(cost__gt=0), name="asset_cost_positive")]
        ordering = ["tag"]

    def __str__(self):
        return f"{self.tag} — {self.name}"


class AssetEstimate(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="estimates")
    version = models.PositiveIntegerField()
    effective_date = models.DateField()
    remaining_months = models.PositiveSmallIntegerField()
    residual = amount()
    carrying_basis = amount()
    reason = models.CharField(max_length=1000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["asset", "version"], name="asset_estimate_version"),
            models.CheckConstraint(
                condition=Q(remaining_months__gte=1, remaining_months__lte=1200, residual__gte=0),
                name="asset_estimate_valid",
            ),
        ]

    def __str__(self):
        return f"{self.asset_id}: estimate v{self.version}"


class DepreciationCharge(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="charges")
    estimate = models.ForeignKey(AssetEstimate, on_delete=models.PROTECT)
    month = models.DateField()
    recognition_date = models.DateField()
    amount = amount()
    journal = models.OneToOneField("accounting.JournalEntry", on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["asset", "month"], name="asset_month_once"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="asset_depreciation_positive"),
        ]

    def __str__(self):
        return f"{self.asset_id}: {self.month:%Y-%m}"


class AssetDisposal(models.Model):
    asset = models.OneToOneField(Asset, on_delete=models.PROTECT, related_name="disposal")
    date = models.DateField()
    kind = models.CharField(
        max_length=16,
        choices=[("sale", "Sale"), ("retirement", "Retirement"), ("write_off", "Write-off")],
    )
    invoice_line = models.OneToOneField(
        "billing.InvoiceLine", null=True, blank=True, on_delete=models.PROTECT
    )
    proceeds_base = amount(default=0)
    accumulated = amount()
    book_value = amount()
    gain_loss = amount()
    journal = models.OneToOneField("accounting.JournalEntry", on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.asset_id}: {self.kind} on {self.date}"


class AssetAction(models.Model):
    operation = models.CharField(max_length=20)
    key = models.CharField(max_length=140, unique=True)
    fingerprint = models.CharField(max_length=64)
    payload = models.JSONField()
    status = models.CharField(max_length=12, default="pending")
    result_id = models.CharField(max_length=100, blank=True)
    approval = models.OneToOneField(
        "approvals.ApprovalRequest", null=True, blank=True, on_delete=models.PROTECT
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.operation}: {self.status}"


class AssetEvidence(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="evidence")
    file = models.ForeignKey("files.StoredFile", on_delete=models.PROTECT)
    description = models.CharField(max_length=500)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description


class CapitalizationReversal(models.Model):
    asset = models.OneToOneField(Asset, on_delete=models.PROTECT, related_name="cancellation")
    date = models.DateField()
    journal = models.OneToOneField("accounting.JournalEntry", on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Capitalization reversal: {self.asset_id}"
