"""Point-in-time commercial recognition, separate from dispatch and invoice issuance.

These are immutable source snapshots/allocations. The accounting journal is the
only ledger. Existing invoice-only contracts remain unchanged.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounting.models import amount
from apps.sales.models import quantity as quantity_field


class FulfillmentPolicy(models.Model):
    order_line = models.OneToOneField(
        "sales.SalesOrderLine", on_delete=models.PROTECT, related_name="recognition_policy"
    )
    trigger = models.CharField(
        max_length=20,
        choices=[
            ("invoice", "Existing invoice treatment"),
            ("control_transfer", "Documented transfer of control"),
        ],
    )
    contract_reference = models.CharField(max_length=200)
    reason = models.CharField(max_length=1000)
    net_contract = amount()
    revenue_account = models.ForeignKey(
        "accounting.Account", on_delete=models.PROTECT, related_name="+"
    )
    snapshot = models.JSONField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order line {self.order_line_id}: {self.trigger}"


class Dispatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey(
        FulfillmentPolicy, on_delete=models.PROTECT, related_name="dispatches"
    )
    date = models.DateField()
    quantity = quantity_field()
    from_location = models.ForeignKey(
        "inventory.Location", on_delete=models.PROTECT, related_name="+"
    )
    transit_location = models.ForeignKey(
        "inventory.Location", on_delete=models.PROTECT, related_name="+"
    )
    reference = models.CharField(max_length=100)
    evidence = models.CharField(max_length=1000)
    movement = models.OneToOneField("inventory.Movement", on_delete=models.PROTECT)
    key = models.CharField(max_length=140, unique=True)
    fingerprint = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="dispatch_quantity_positive")
        ]

    def __str__(self):
        return self.reference


class ControlTransfer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey(
        FulfillmentPolicy, on_delete=models.PROTECT, related_name="transfers"
    )
    dispatch = models.ForeignKey(
        Dispatch, null=True, blank=True, on_delete=models.PROTECT, related_name="transfers"
    )
    location = models.ForeignKey("inventory.Location", on_delete=models.PROTECT)
    date = models.DateField()
    quantity = quantity_field()
    reference = models.CharField(max_length=100)
    evidence = models.CharField(max_length=1000)
    currency = models.CharField(max_length=3)
    net_native = amount(default=0)
    base_revenue = amount(default=0)
    base_cogs = amount(default=0)
    cogs_account = models.ForeignKey(
        "accounting.Account", on_delete=models.PROTECT, related_name="+"
    )
    unbilled_quantity = quantity_field(default=0)
    unbilled_native = amount(default=0)
    unbilled_base = amount(default=0)
    deferred_snapshot = models.JSONField(default=list, blank=True)
    journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT
    )
    movement = models.OneToOneField(
        "inventory.Movement", null=True, blank=True, on_delete=models.PROTECT
    )
    key = models.CharField(max_length=140, unique=True)
    fingerprint = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0, base_cogs__gte=0, base_revenue__gte=0),
                name="control_transfer_positive",
            )
        ]

    def __str__(self):
        return self.reference


class InvoiceRecognitionBinding(models.Model):
    invoice_line = models.OneToOneField(
        "billing.InvoiceLine", on_delete=models.PROTECT, related_name="recognition_binding"
    )
    policy = models.ForeignKey(FulfillmentPolicy, on_delete=models.PROTECT, related_name="bindings")
    unbilled_quantity = quantity_field(default=0)
    unbilled_native = amount(default=0)
    unbilled_base = amount(default=0)
    deferred_quantity = quantity_field(default=0)
    deferred_native = amount(default=0)
    deferred_base = amount(default=0)
    unbilled_snapshot = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Recognition allocation for invoice line {self.invoice_line_id}"


class DeferredCreditAllocation(models.Model):
    credit_line = models.OneToOneField(
        "billing.CreditNoteLine", on_delete=models.PROTECT, related_name="deferred_allocation"
    )
    binding = models.ForeignKey(
        InvoiceRecognitionBinding, on_delete=models.PROTECT, related_name="credits"
    )
    native = amount()
    base = amount()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Deferred credit {self.credit_line_id}"


class CustomerReturn(models.Model):
    transfer = models.ForeignKey(ControlTransfer, on_delete=models.PROTECT, related_name="returns")
    date = models.DateField()
    quantity = quantity_field()
    base_cost = amount()
    location = models.ForeignKey("inventory.Location", on_delete=models.PROTECT)
    movement = models.OneToOneField(
        "inventory.Movement", null=True, blank=True, on_delete=models.PROTECT
    )
    reason = models.CharField(max_length=1000)
    reference = models.CharField(max_length=100)
    key = models.CharField(max_length=140, unique=True)
    fingerprint = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0, base_cost__gte=0), name="customer_return_positive"
            )
        ]

    def __str__(self):
        return self.reference


class DispatchRecall(models.Model):
    dispatch = models.ForeignKey(Dispatch, on_delete=models.PROTECT, related_name="recalls")
    date = models.DateField()
    quantity = quantity_field()
    location = models.ForeignKey("inventory.Location", on_delete=models.PROTECT)
    movement = models.OneToOneField("inventory.Movement", on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000)
    key = models.CharField(max_length=140, unique=True)
    fingerprint = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="dispatch_recall_positive")
        ]

    def __str__(self):
        return f"Dispatch recall {self.dispatch_id}"
