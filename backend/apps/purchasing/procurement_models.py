"""Procurement source records. Purchase orders never post a journal."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounting.models import amount, rate
from apps.sales.models import quantity as quantity_field


class PurchaseOrder(models.Model):
    number = models.CharField(max_length=80, unique=True)
    vendor = models.ForeignKey("purchasing.Vendor", on_delete=models.PROTECT, related_name="orders")
    date = models.DateField()
    expected_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3)
    prices_include_tax = models.BooleanField(default=False)
    notes = models.CharField(max_length=1000, blank=True)
    status = models.CharField(
        max_length=24,
        choices=[
            ("draft", "Draft"),
            ("pending", "Awaiting approval"),
            ("approved", "Approved"),
            ("issued", "Issued"),
            ("partial", "Partially received"),
            ("received", "Received"),
            ("closed", "Closed"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
    )
    revision = models.PositiveIntegerField(default=1)
    taxable = amount(default=0)
    tax = amount(default=0)
    total = amount(default=0)
    approval = models.ForeignKey(
        "approvals.ApprovalRequest", null=True, blank=True, on_delete=models.PROTECT
    )
    revised_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    closing_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-date", "-pk"]

    def __str__(self):
        return self.number


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="lines")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey("sales.BillingItem", on_delete=models.PROTECT)
    description = models.CharField(max_length=500)
    quantity = quantity_field()
    unit_price = amount()
    tax_code = models.ForeignKey(
        "accounting.TaxCode", null=True, blank=True, on_delete=models.PROTECT
    )
    taxable = amount()
    tax = amount()
    total = amount()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["order", "position"], name="po_line_position"),
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_price__gte=0), name="po_line_positive"
            ),
        ]

    def __str__(self):
        return f"{self.order_id}:{self.position}"


class PurchaseOrderSnapshot(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="snapshots")
    revision = models.PositiveIntegerField()
    snapshot = models.JSONField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "revision"], name="po_snapshot_revision")
        ]

    def __str__(self):
        return f"{self.order_id}:v{self.revision}"


class GoodsReceipt(models.Model):
    order_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, related_name="receipts"
    )
    date = models.DateField()
    quantity = quantity_field()
    rejected_quantity = quantity_field(default=0)
    kind = models.CharField(
        max_length=12, choices=[("goods", "Goods"), ("service", "Service acceptance")]
    )
    location = models.ForeignKey(
        "inventory.Location", null=True, blank=True, on_delete=models.PROTECT
    )
    reference = models.CharField(max_length=100)
    reason = models.CharField(max_length=500)
    evidence = models.ForeignKey(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT
    )
    exchange_rate = rate()
    native_value = amount()
    base_value = amount()
    movement = models.OneToOneField(
        "inventory.Movement", null=True, blank=True, on_delete=models.PROTECT
    )
    key = models.CharField(max_length=140, unique=True)
    fingerprint = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0, rejected_quantity__gte=0),
                name="receipt_quantity_positive",
            )
        ]

    def __str__(self):
        return self.reference


class ReceiptBillMatch(models.Model):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, related_name="bill_matches")
    bill_line = models.ForeignKey(
        "purchasing.VendorBillLine", on_delete=models.PROTECT, related_name="receipt_matches"
    )
    quantity = quantity_field()
    native_value = amount()
    base_value = amount()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["receipt", "bill_line"], name="receipt_bill_line_once"),
            models.CheckConstraint(
                condition=Q(quantity__gt=0, native_value__gt=0, base_value__gt=0),
                name="receipt_match_positive",
            ),
        ]

    def __str__(self):
        return f"{self.receipt_id}:{self.bill_line_id}"


class SupplierReturn(models.Model):
    """Accepted cancellation of an unmatched acquisition, with historical provenance."""

    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, related_name="returns")
    date = models.DateField()
    quantity = quantity_field()
    native_value = amount()
    base_value = amount()
    inventory_value = amount()
    variance = amount()
    variance_account = models.ForeignKey("accounting.Account", on_delete=models.PROTECT)
    basis = models.JSONField()
    reference = models.CharField(max_length=100)
    reason = models.CharField(max_length=500)
    key = models.CharField(max_length=140, unique=True)
    fingerprint = models.CharField(max_length=64)
    movement = models.OneToOneField("inventory.Movement", on_delete=models.PROTECT)
    journal = models.OneToOneField("accounting.JournalEntry", on_delete=models.PROTECT)
    approval = models.OneToOneField(
        "approvals.ApprovalRequest", null=True, blank=True, on_delete=models.PROTECT
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    quantity__gt=0, native_value__gte=0, base_value__gte=0, inventory_value__gte=0
                ),
                name="supplier_return_positive",
            )
        ]

    def __str__(self):
        return self.reference


class ProcurementEvidence(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="evidence")
    receipt = models.ForeignKey(GoodsReceipt, null=True, blank=True, on_delete=models.PROTECT)
    file = models.ForeignKey("files.StoredFile", on_delete=models.PROTECT)
    description = models.CharField(max_length=500)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description


class ReceiptCostCorrection(models.Model):
    receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.PROTECT, related_name="cost_corrections"
    )
    date = models.DateField()
    native_delta = amount()
    base_delta = amount()
    inventory_delta = amount()
    consumed_delta = amount()
    variance_account = models.ForeignKey("accounting.Account", on_delete=models.PROTECT)
    basis = models.JSONField()
    reason = models.CharField(max_length=1000)
    key = models.CharField(max_length=140, unique=True)
    fingerprint = models.CharField(max_length=64)
    journal = models.OneToOneField("accounting.JournalEntry", on_delete=models.PROTECT)
    movement = models.OneToOneField(
        "inventory.Movement", null=True, blank=True, on_delete=models.PROTECT
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Receipt {self.receipt_id} cost correction"
