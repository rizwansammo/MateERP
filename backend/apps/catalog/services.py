"""Validated catalog edits and exact dated quotations; no financial postings."""

from decimal import ROUND_HALF_UP, Decimal, localcontext

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.accounting.models import Account, TaxCode
from apps.accounting.money import decimal, money
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import require
from apps.audit.services import record
from apps.core.exceptions import BusinessRuleViolation
from apps.purchasing.models import Vendor
from apps.sales.models import BillingItem
from apps.sales.services import _get, enabled_currency

from .models import Category, ItemProfile, PriceRevision, Unit


@transaction.atomic
def save_reference(request, model, data, pk=None):
    require(request.user, "catalog.manage")
    lock_company()
    obj = _get(model, pk) if pk else model()
    if pk and "code" in data and data["code"].upper() != obj.code:
        raise BusinessRuleViolation("Reference codes cannot be renamed; create another instead.")
    if (
        model is Unit
        and pk
        and data.get("allows_fraction", obj.allows_fraction) != obj.allows_fraction
        and ItemProfile.objects.filter(unit=obj).exists()
    ):
        raise BusinessRuleViolation("An assigned unit's quantity semantics cannot change.")
    for field in ("code", "name", "is_active", "allows_fraction"):
        if field in data and hasattr(obj, field):
            setattr(obj, field, data[field])
    obj.code = obj.code.strip().upper()
    obj.full_clean()
    obj.save()
    record("catalog.reference_saved", request=request, target=obj, after=data)
    return obj


def _account(pk, types, control=""):
    if pk is None:
        return None
    account = Account.objects.filter(pk=pk, is_active=True, is_postable=True).first()
    if account is None or account.account_type not in types or account.control != control:
        raise ValidationError(
            {"account": "Choose an active posting account of the required purpose."}
        )
    return account


@transaction.atomic
def save_item(request, data, pk=None):
    require(request.user, "catalog.manage")
    lock_company()
    item = _get(BillingItem, pk) if pk else BillingItem()
    profile = ItemProfile.objects.select_for_update().filter(item=item).first() if pk else None
    if profile and data.get("revision") != profile.revision:
        raise BusinessRuleViolation(
            "This catalog item changed. Reload before saving.", code="stale_revision"
        )
    if profile is None:
        profile = ItemProfile(item=item)
    unit = _get(Unit, data.get("unit_id", profile.unit_id))
    category_id = data.get("category_id", profile.category_id)
    category = _get(Category, category_id) if category_id else None
    if not unit.is_active or (category and not category.is_active):
        raise ValidationError({"unit_id": "Use active units and categories."})
    kind = data.get("kind", profile.kind)
    # A profile's unit/kind is its operational identity. Changing it after creation
    # would reinterpret historical quantities; create an explicit replacement SKU.
    if profile.pk and (unit.pk != profile.unit_id or kind != profile.kind):
        raise BusinessRuleViolation("An established item retains its kind and unit. Use a new SKU.")
    for field in ("code", "name", "description", "currency", "is_active"):
        if field in data:
            setattr(item, field, data[field])
    item.code = item.code.strip().upper()
    item.unit = unit.code
    enabled_currency(item.currency)
    if "unit_price" in data:
        item.unit_price = decimal(data["unit_price"], "unit_price")
    if "revenue_account_id" in data:
        item.revenue_account = _account(data["revenue_account_id"], {"revenue"})
    if "tax_code_id" in data:
        item.tax_code = _get(TaxCode, data["tax_code_id"]) if data["tax_code_id"] else None
    item.full_clean()
    item.save()
    profile.item = item
    profile.kind, profile.unit, profile.category = kind, unit, category
    profile.reorder_level = decimal(
        data.get("reorder_level", profile.reorder_level), "reorder_level"
    )
    for field, types, control in (
        ("purchase_account", {"expense", "asset"}, ""),
        ("cogs_account", {"expense"}, ""),
        ("inventory_account", {"asset"}, "inventory"),
    ):
        if f"{field}_id" in data:
            setattr(profile, field, _account(data[f"{field}_id"], types, control))
    if "preferred_vendor_id" in data:
        profile.preferred_vendor = (
            _get(Vendor, data["preferred_vendor_id"]) if data["preferred_vendor_id"] else None
        )
    if profile.pk:
        profile.revision += 1
    profile.full_clean()
    profile.save()
    record("catalog.item_saved", request=request, target=item, after=data)
    return item


@transaction.atomic
def add_price(request, item_id, data):
    require(request.user, "catalog.manage")
    lock_company()
    item = _get(BillingItem, item_id)
    enabled_currency(data["currency"])
    value = decimal(data["value"], "value")
    price = PriceRevision(item=item, created_by=request.user, **{**data, "value": value})
    price.full_clean()
    price.save()
    record("catalog.price_added", request=request, target=price, after=data)
    return price


def quote(item, *, on, currency, purpose="sale", quantity="1"):
    """Read-only quotation; document services still freeze their calculated snapshots."""
    enabled_currency(currency)
    qty = decimal(quantity, "quantity")
    if qty <= 0:
        raise ValidationError({"quantity": "Enter a positive quantity."})
    profile = ItemProfile.objects.select_related("unit").filter(item=item).first()
    if profile and not profile.unit.allows_fraction and qty != qty.to_integral_value():
        raise ValidationError({"quantity": "This unit requires whole quantities."})
    price = item.prices.filter(purpose=purpose, currency=currency, effective_date__lte=on).first()
    if price is None and (purpose != "sale" or item.currency != currency):
        raise ValidationError(
            {"currency": "No dated price is available for this currency/purpose."}
        )
    value = price.value if price else item.unit_price
    from apps.accounting.money import quantum

    with localcontext() as ctx:
        ctx.prec = 60
        subtotal = (value * qty).quantize(quantum(currency), rounding=ROUND_HALF_UP)
    return {
        "item_id": item.pk,
        "date": on,
        "currency": currency,
        "purpose": purpose,
        "quantity": qty,
        "unit_price": value,
        "subtotal": subtotal,
        "includes_tax": price.includes_tax if price else False,
        "price_revision_id": price.pk if price else None,
        "basis": "dated_price" if price else "legacy_item_price",
    }


def margin(item, *, on, currency, sale, cost):
    """Exact scenario preview, explicitly separate from realized historical margin."""
    enabled_currency(currency)
    selling, purchase = money(sale, currency), money(cost, currency)
    difference = selling - purchase
    with localcontext() as ctx:
        ctx.prec = 60
        percent = (difference / selling * 100).quantize(Decimal("0.000001")) if selling else None
    return {
        "item_id": item.pk,
        "date": on,
        "currency": currency,
        "sale": selling,
        "cost": purchase,
        "margin": difference,
        "percent": percent,
        "realized": False,
    }
