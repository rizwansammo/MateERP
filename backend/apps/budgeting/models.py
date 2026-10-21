from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounting.models import amount


class CostCenter(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    owner_reference = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=100, blank=True)
    categories = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class AnalyticalClassification(models.Model):
    line = models.ForeignKey(
        "accounting.JournalLine",
        on_delete=models.PROTECT,
        related_name="analytical_classifications",
    )
    version = models.PositiveIntegerField()
    cost_center = models.ForeignKey(CostCenter, null=True, blank=True, on_delete=models.PROTECT)
    project = models.ForeignKey("sales.Project", null=True, blank=True, on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["line", "version"], name="analysis_line_version")
        ]

    def __str__(self):
        return f"Line {self.line_id}: classification v{self.version}"


class Budget(models.Model):
    name = models.CharField(max_length=150)
    fiscal_year = models.ForeignKey("accounting.FiscalYear", on_delete=models.PROTECT)
    owner_reference = models.CharField(max_length=150, blank=True)
    is_archived = models.BooleanField(default=False)
    active_revision = models.ForeignKey(
        "BudgetRevision", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    original_revision = models.ForeignKey(
        "BudgetRevision", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class BudgetRevision(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name="revisions")
    version = models.PositiveIntegerField()
    notes = models.CharField(max_length=1000)
    status = models.CharField(max_length=12, default="draft")
    approval = models.OneToOneField(
        "approvals.ApprovalRequest", null=True, blank=True, on_delete=models.PROTECT
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["budget", "version"], name="budget_revision_version")
        ]

    def __str__(self):
        return f"Budget {self.budget_id}: v{self.version}"


class BudgetLine(models.Model):
    revision = models.ForeignKey(BudgetRevision, on_delete=models.PROTECT, related_name="lines")
    month = models.DateField()
    account = models.ForeignKey("accounting.Account", on_delete=models.PROTECT)
    category = models.CharField(
        max_length=12,
        choices=[
            ("operating", "Operating expense"),
            ("cogs", "Cost of sales"),
            ("capex", "Capital additions"),
            ("tax", "Recoverable tax"),
        ],
    )
    cost_center = models.ForeignKey(CostCenter, null=True, blank=True, on_delete=models.PROTECT)
    project = models.ForeignKey("sales.Project", null=True, blank=True, on_delete=models.PROTECT)
    amount = amount()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="budget_amount_nonnegative")
        ]

    def __str__(self):
        return f"{self.month}: account {self.account_id}"


class BudgetPublication(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name="publications")
    revision = models.OneToOneField(BudgetRevision, on_delete=models.PROTECT)
    previous = models.ForeignKey(
        BudgetRevision, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Budget {self.budget_id}: published revision {self.revision_id}"
