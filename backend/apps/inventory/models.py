import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounting.models import amount
from apps.sales.models import quantity


class Location(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name


class Movement(models.Model):
    """Immutable physical/cost event. Aggregates are selectors, never cached balances."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sequence = models.PositiveBigIntegerField(unique=True)
    item = models.ForeignKey(
        "sales.BillingItem", on_delete=models.PROTECT, related_name="stock_moves"
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="movements")
    date = models.DateField()
    kind = models.CharField(
        max_length=24,
        choices=[
            ("receipt", "Goods receipt"),
            ("issue", "Issue"),
            ("return", "Customer return"),
            ("supplier_return", "Supplier return"),
            ("transfer_out", "Transfer out"),
            ("transfer_in", "Transfer in"),
            ("count", "Count adjustment"),
            ("opening", "Opening"),
            ("price_adjustment", "Acquisition cost adjustment"),
        ],
    )
    quantity = quantity()
    base_value = amount()
    source_type = models.CharField(max_length=40)
    source_id = models.CharField(max_length=160)
    source_key = models.CharField(max_length=160, unique=True)
    fingerprint = models.CharField(max_length=64)
    reason = models.CharField(max_length=500)
    original = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    journal = models.ForeignKey(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sequence"]
        indexes = [
            models.Index(fields=["item", "date"]),
            models.Index(fields=["source_type", "source_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(quantity=0) | ~Q(base_value=0), name="stock_move_nonzero"
            ),
        ]

    def __str__(self):
        return f"{self.sequence}:{self.kind}:{self.item_id}"


class StockCount(models.Model):
    """Frozen count and valuation basis; the movement is the resulting cost event."""

    payload = models.JSONField()
    basis = models.JSONField()
    key = models.CharField(max_length=140, unique=True)
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(
        max_length=12,
        default="pending",
        choices=[
            ("pending", "Pending approval"),
            ("posted", "Posted"),
            ("rejected", "Rejected / withdrawn"),
        ],
    )
    approval = models.ForeignKey(
        "approvals.ApprovalRequest", null=True, blank=True, on_delete=models.PROTECT
    )
    movement = models.OneToOneField(Movement, null=True, blank=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Stock count {self.pk}"
