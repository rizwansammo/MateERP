from django.conf import settings
from django.db import models
from django.db.models import Q


class ApprovalPolicy(models.Model):
    """A simple approval rule for one category of action."""

    category = models.CharField(max_length=32, unique=True)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    approver_role = models.ForeignKey(
        "accounts.Role", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    amount_threshold = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    allow_self_approval = models.BooleanField(default=False)
    notes = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        verbose_name_plural = "approval policies"
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_threshold__isnull=True) | Q(amount_threshold__gte=0),
                name="approval_threshold_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.category

    @property
    def in_force(self) -> bool:
        return self.is_active and self.is_required


class ApprovalRequest(models.Model):
    """A request waiting for (or having received) an approval decision.

    ``payload`` is the exact change that was requested, captured at request
    time, so later edits cannot alter what the approver approves.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    category = models.CharField(max_length=32)
    action = models.CharField(max_length=64)
    subject_key = models.CharField(max_length=100, default="", blank=True)
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    payload = models.JSONField(default=dict)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="approval_requests"
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    request_reason = models.CharField(max_length=500, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.CharField(max_length=500, blank=True)
    result_reference = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status="pending", reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | Q(
                        status__in=["approved", "rejected"],
                        reviewed_by__isnull=False,
                        reviewed_at__isnull=False,
                    )
                    | Q(status="cancelled", reviewed_at__isnull=False)
                ),
                name="approval_status_consistent",
            ),
            models.UniqueConstraint(
                fields=["action", "subject_key"],
                condition=Q(status="pending"),
                name="one_pending_per_subject",
            ),
        ]
        indexes = [models.Index(fields=["status", "-requested_at"], name="approval_status_idx")]

    def __str__(self) -> str:
        return self.title
