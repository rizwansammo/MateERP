"""Commercial master data and sales orders. Nothing here posts to the ledger."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounting.models import amount


def quantity(**kwargs):
    return models.DecimalField(max_digits=18, decimal_places=6, **kwargs)


def percent(**kwargs):
    return models.DecimalField(max_digits=9, decimal_places=6, **kwargs)


class Customer(models.Model):
    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    tax_id = models.CharField(max_length=60, blank=True)
    address = models.CharField(max_length=500, blank=True)
    city = models.CharField(max_length=80, blank=True)
    country = models.CharField(max_length=80, blank=True)
    currency = models.CharField(max_length=3)
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    notes = models.CharField(max_length=1000, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(payment_terms_days__lte=365), name="customer_terms_range"
            )
        ]

    def __str__(self):
        return self.name


class CustomerContact(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="contacts")
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_primary", "name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer"],
                condition=Q(is_primary=True, is_active=True),
                name="one_primary_contact",
            )
        ]

    def __str__(self):
        return self.name


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    reference = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="projects")
    currency = models.CharField(max_length=3)
    contract_value = amount(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    notes = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["reference"]
        constraints = [
            models.CheckConstraint(condition=Q(contract_value__gte=0), name="project_value_nonneg")
        ]

    def __str__(self):
        return self.reference


class Milestone(models.Model):
    """A billable share of a project's contract. Billing links live on the invoice side."""

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="milestones")
    position = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=160)
    percent = percent()
    amount = amount()

    class Meta:
        ordering = ["project", "position"]
        constraints = [
            models.UniqueConstraint(fields=["project", "position"], name="milestone_position"),
            models.CheckConstraint(
                condition=Q(percent__gt=0, percent__lte=100, amount__gte=0),
                name="milestone_share_valid",
            ),
        ]

    def __str__(self):
        return f"{self.project_id}:{self.name}"


class BillingItem(models.Model):
    """Minimal reusable invoice line. The full product & service catalog is Phase 6."""

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=500, blank=True)
    unit = models.CharField(max_length=20, default="unit")
    unit_price = amount(default=0)
    currency = models.CharField(max_length=3)
    revenue_account = models.ForeignKey(
        "accounting.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    tax_code = models.ForeignKey(
        "accounting.TaxCode", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="item_price_nonneg")
        ]

    def __str__(self):
        return self.name


class SalesOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        PARTIALLY_INVOICED = "partially_invoiced", "Partially invoiced"
        INVOICED = "invoiced", "Fully invoiced"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=80, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.PROTECT, related_name="orders"
    )
    order_date = models.DateField()
    currency = models.CharField(max_length=3)
    title = models.CharField(max_length=200, blank=True)
    customer_reference = models.CharField(max_length=80, blank=True)
    prices_include_tax = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.CharField(max_length=1000, blank=True)
    # Server-calculated when the lines are saved (display only; orders never post).
    tax = amount(default=0)
    total = amount(default=0)
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-order_date", "-pk"]

    def __str__(self):
        return self.number


class SalesOrderLine(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="lines")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(
        BillingItem, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    description = models.CharField(max_length=500)
    quantity = quantity()
    unit_price = amount()
    discount_type = models.CharField(
        max_length=8, choices=[("percent", "Percent"), ("fixed", "Fixed")], default="percent"
    )
    discount_value = amount(default=0)
    tax_code = models.ForeignKey(
        "accounting.TaxCode", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["order", "position"]
        constraints = [
            models.UniqueConstraint(fields=["order", "position"], name="order_line_position"),
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_price__gte=0, discount_value__gte=0),
                name="order_line_amounts_valid",
            ),
        ]

    def __str__(self):
        return f"{self.order_id}:{self.position}"
