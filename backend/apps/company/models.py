from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

SINGLETON_ID = 1


class CompanyProfile(models.Model):
    """The one company this installation belongs to.

    A check constraint pins the primary key to 1, so the database itself
    rejects a second company. Registration details are optional: the company
    may be an unregistered business.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_ID, editable=False)
    display_name = models.CharField(max_length=120)
    legal_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    website = models.URLField(max_length=200, blank=True)
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)
    tax_id = models.CharField(max_length=60, blank=True)
    registration_number = models.CharField(max_length=60, blank=True)
    base_currency = models.CharField(max_length=3, default="BDT")
    time_zone = models.CharField(max_length=64, default="Asia/Dhaka")
    fiscal_year_start_month = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    notes = models.TextField(max_length=2000, blank=True)
    logo = models.ForeignKey(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=SINGLETON_ID), name="company_profile_singleton"),
            models.CheckConstraint(
                condition=Q(fiscal_year_start_month__gte=1, fiscal_year_start_month__lte=12),
                name="company_fiscal_month_range",
            ),
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def address_lines(self) -> list[str]:
        locality = " ".join(p for p in (self.city, self.postal_code) if p)
        parts = [
            self.address_line1,
            self.address_line2,
            ", ".join(p for p in (locality, self.region) if p),
            self.country,
        ]
        return [p for p in parts if p]


class BusinessSettings(models.Model):
    """Installation-wide business configuration (singleton).

    Tax values are stored configuration only; no tax is calculated until the
    accounting and billing phases.
    """

    class CurrencyDisplay(models.TextChoices):
        SYMBOL = "symbol", "Symbol (৳1,250.00)"
        CODE = "code", "Code (BDT 1,250.00)"

    class NumberGrouping(models.TextChoices):
        INTERNATIONAL = "international", "1,234,567.00"
        SOUTH_ASIAN = "south_asian", "12,34,567.00"

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_ID, editable=False)
    currency_display = models.CharField(
        max_length=16, choices=CurrencyDisplay.choices, default=CurrencyDisplay.SYMBOL
    )
    number_grouping = models.CharField(
        max_length=16, choices=NumberGrouping.choices, default=NumberGrouping.SOUTH_ASIAN
    )
    enabled_currencies = ArrayField(models.CharField(max_length=3), default=list, blank=True)
    tax_registered = models.BooleanField(default=False)
    tax_label = models.CharField(max_length=20, default="VAT")
    tax_registration_label = models.CharField(max_length=40, default="BIN")
    default_tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    prices_include_tax = models.BooleanField(default=False)
    numbering = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        verbose_name_plural = "business settings"
        constraints = [
            models.CheckConstraint(
                condition=Q(id=SINGLETON_ID), name="business_settings_singleton"
            ),
        ]

    def __str__(self) -> str:
        return "Business settings"


class ModuleSetting(models.Model):
    """Whether an optional module is enabled. Disabling never deletes records."""

    key = models.CharField(max_length=32, unique=True)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    def __str__(self) -> str:
        return f"{self.key}: {'on' if self.enabled else 'off'}"
