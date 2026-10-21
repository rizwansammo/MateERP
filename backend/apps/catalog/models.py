"""Commercial profiles extend, rather than replace, existing billing-item identities."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounting.models import amount
from apps.sales.models import quantity


class Category(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name


class Unit(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=80)
    allows_fraction = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class ItemProfile(models.Model):
    class Kind(models.TextChoices):
        STOCK = "stock", "Tracked product"
        NONSTOCK = "nonstock", "Non-stock product"
        SERVICE = "service", "Service"

    item = models.OneToOneField(
        "sales.BillingItem", on_delete=models.PROTECT, related_name="profile"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NONSTOCK)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    purchase_account = models.ForeignKey(
        "accounting.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cogs_account = models.ForeignKey(
        "accounting.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    inventory_account = models.ForeignKey(
        "accounting.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    preferred_vendor = models.ForeignKey(
        "purchasing.Vendor", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reorder_level = quantity(default=0)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(reorder_level__gte=0), name="catalog_reorder_nonneg")
        ]

    def __str__(self):
        return f"Catalog profile {self.item_id}"


class PriceRevision(models.Model):
    """Append-only prices. A later effective date supersedes earlier quotes, never history."""

    item = models.ForeignKey("sales.BillingItem", on_delete=models.PROTECT, related_name="prices")
    purpose = models.CharField(max_length=8, choices=[("sale", "Sale"), ("purchase", "Purchase")])
    effective_date = models.DateField()
    currency = models.CharField(max_length=3)
    value = amount()
    includes_tax = models.BooleanField(default=False)
    reason = models.CharField(max_length=500)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "purpose", "currency", "effective_date"], name="catalog_price_date"
            ),
            models.CheckConstraint(condition=Q(value__gte=0), name="catalog_price_nonneg"),
        ]

    def __str__(self):
        return f"{self.item_id}:{self.purpose}:{self.effective_date}"
