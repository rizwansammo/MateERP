"""Serialized weighted-average stock events backed by the one authoritative ledger."""

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal, localcontext

from django.db import transaction
from django.db.models import Max, Sum
from rest_framework.exceptions import ValidationError

from apps.accounting.models import Account, AccountingPeriod, JournalLine
from apps.accounting.money import ZERO, decimal, money, quantum, strings
from apps.accounting.services.adapters import authorize
from apps.accounting.services.posting import post_journal
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import require
from apps.audit.services import record
from apps.catalog.models import ItemProfile
from apps.company.services import is_module_enabled
from apps.core.exceptions import BusinessRuleViolation
from apps.sales.services import _get

from .models import Location, Movement


def enabled():
    if not is_module_enabled("inventory"):
        raise BusinessRuleViolation("Inventory is disabled. Historical stock remains available.")


def fingerprint(data):
    return hashlib.sha256(
        json.dumps(strings(data), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def control(purpose):
    account = Account.objects.filter(control=purpose, is_active=True, is_postable=True).first()
    if account is None:
        raise BusinessRuleViolation(
            f"Configure the {purpose.replace('_', ' ')} control account first."
        )
    return account


def position(item_id, location_id=None, on=None):
    qs = Movement.objects.filter(item_id=item_id)
    if location_id is not None:
        qs = qs.filter(location_id=location_id)
    if on is not None:
        qs = qs.filter(date__lte=on)
    total = qs.aggregate(quantity=Sum("quantity"), value=Sum("base_value"))
    qty, value = total["quantity"] or ZERO, total["value"] or ZERO
    with localcontext() as ctx:
        ctx.prec = 60
        average = (
            (value / qty).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP) if qty else ZERO
        )
    return {"quantity": qty, "value": value, "average_cost": average}


def issue_cost(item_id, qty, base):
    pool = position(item_id)
    if qty > pool["quantity"]:
        raise BusinessRuleViolation(
            "The issue exceeds available company stock.", code="insufficient_stock"
        )
    if qty == pool["quantity"]:
        return pool["value"]
    with localcontext() as ctx:
        ctx.prec = 60
        return (pool["value"] * qty / pool["quantity"]).quantize(
            quantum(base), rounding=ROUND_HALF_UP
        )


@transaction.atomic
def save_location(request, data, pk=None):
    require(request.user, "inventory.manage")
    lock_company()
    enabled()
    obj = _get(Location, pk) if pk else Location()
    if pk and data.get("is_active") is False:
        occupied = obj.movements.values("item_id").annotate(qty=Sum("quantity")).exclude(qty=0)
        if occupied.exists():
            raise BusinessRuleViolation(
                "Transfer or resolve this location's stock before deactivation."
            )
    for key in ("code", "name", "address", "is_active"):
        if key in data:
            setattr(obj, key, data[key])
    obj.code = obj.code.upper().strip()
    obj.full_clean()
    obj.save()
    record("inventory.location_saved", request=request, target=obj, after=data)
    return obj


def _validate(item_id, location_id, on, qty):
    if (
        not qty.is_finite()
        or abs(qty) >= Decimal("1000000000000")
        or qty != qty.quantize(Decimal("0.000001"))
    ):
        raise ValidationError({"quantity": "Use at most 12 whole and six decimal quantity digits."})
    if not AccountingPeriod.objects.filter(
        start__lte=on, end__gte=on, is_closed=False, fiscal_year__is_closed=False
    ).exists():
        raise BusinessRuleViolation(
            "Stock events require an open accounting period.", code="period_closed"
        )
    profile = ItemProfile.objects.select_related("item", "unit").filter(item_id=item_id).first()
    location = _get(Location, location_id)
    if not profile or profile.kind != "stock" or not profile.item.is_active:
        raise ValidationError({"item_id": "Choose an active tracked product."})
    if not location.is_active:
        raise ValidationError({"location_id": "Choose an active location."})
    if not profile.unit.allows_fraction and qty != qty.to_integral_value():
        raise ValidationError({"quantity": "This item's unit requires whole quantities."})
    last = Movement.objects.filter(item_id=item_id).order_by("-date", "-sequence").first()
    if last and on < last.date:
        raise BusinessRuleViolation(
            "This date precedes the latest stock event. "
            "Use a documented current-period correction.",
            code="stock_chronology",
        )
    if profile.inventory_account_id != control("inventory").pk:
        raise ValidationError(
            {"item_id": "Assign this item to the inventory control account first."}
        )
    return profile


def _persist(
    request,
    *,
    item_id,
    location_id,
    on,
    kind,
    qty,
    value,
    key,
    source_type,
    source_id,
    reason,
    digest,
    journal=None,
    original=None,
):
    sequence = (Movement.objects.aggregate(last=Max("sequence"))["last"] or 0) + 1
    obj = Movement.objects.create(
        sequence=sequence,
        item_id=item_id,
        location_id=location_id,
        date=on,
        kind=kind,
        quantity=qty,
        base_value=value,
        source_key=key,
        source_type=source_type,
        source_id=str(source_id),
        reason=reason,
        fingerprint=digest,
        journal=journal,
        original=original,
        created_by=request.user,
    )
    record(
        "inventory.movement_posted",
        request=request,
        target=obj,
        after={"item": item_id, "kind": kind, "quantity": qty, "value": value, "source": key},
    )
    return obj


def _replay(key, digest):
    previous = Movement.objects.filter(source_key=key).first()
    if previous and previous.fingerprint != digest:
        raise BusinessRuleViolation(
            "This operation key was used with different content.", code="idempotency_conflict"
        )
    return previous


@transaction.atomic
def receive(
    request,
    *,
    item_id,
    location_id,
    on,
    qty,
    value,
    key,
    source_type,
    source_id,
    authority,
    reason,
    offset=None,
    kind="receipt",
    original=None,
):
    """Internal receiving adapter; the source validates its economics and authority."""
    company = lock_company()
    enabled()
    authority.verify(request.user, source_type, "receive")
    qty, value = decimal(qty, "quantity"), money(value, company.base_currency)
    if qty <= 0 or value < 0 or (value == 0 and kind != "return"):
        raise ValidationError({"quantity": "Receipt quantity and value must be positive."})
    digest = fingerprint(
        {
            **locals_payload(item_id, location_id, on, qty, value, reason),
            "kind": kind,
            "original": str(original.pk) if original else None,
        }
    )
    if previous := _replay(key, digest):
        return previous
    _validate(item_id, location_id, on, qty)
    offset = offset or control("grni")
    journal = (
        post_journal(
            actor=request.user,
            authority=authority,
            request_context=request,
            source_type=source_type,
            source_id=source_id,
            source_action="receive",
            posting_key=key,
            posting_date=on,
            description=reason,
            lines=[
                {
                    "account_id": control("inventory").pk,
                    "currency": company.base_currency,
                    "debit": str(value),
                },
                {"account_id": offset.pk, "currency": company.base_currency, "credit": str(value)},
            ],
        )
        if value
        else None
    )
    return _persist(
        request,
        item_id=item_id,
        location_id=location_id,
        on=on,
        kind=kind,
        qty=qty,
        value=value,
        key=key,
        source_type=source_type,
        source_id=source_id,
        reason=reason,
        digest=digest,
        journal=journal,
        original=original,
    )


def locals_payload(item_id, location_id, on, qty, value, reason):
    return {
        "item": item_id,
        "location": location_id,
        "date": on,
        "quantity": qty,
        "value": value,
        "reason": reason,
    }


@transaction.atomic
def adjust(request, data, *, reviewed_count=None):
    require(request.user, "inventory.post", "inventory.manage", "finance.view")
    company = lock_company()
    enabled()
    if reviewed_count is None:
        from apps.approvals.services import policy_for_action

        policy = policy_for_action("stock_count.post")
        if policy and policy.in_force:
            raise BusinessRuleViolation(
                "Submit a retained stock count for review before posting adjustments."
            )
    qty = decimal(data["quantity"], "quantity", signed=True)
    valuation = data.get("kind") == "valuation"
    if valuation:
        require(request.user, "accounting.manage")
    digest = fingerprint(data)
    key = data["key"]
    if previous := _replay(key, digest):
        return previous
    profile = _validate(data["item_id"], data["location_id"], data["date"], qty)
    if qty == 0 and not valuation:
        raise ValidationError({"quantity": "Enter a nonzero adjustment."})
    original = _get(Movement, data["correction_of_id"]) if data.get("correction_of_id") else None
    if original and (original.item_id != profile.item_id or original.date > data["date"]):
        raise ValidationError({"correction_of_id": "Select an earlier event for this product."})
    # A counted balance is frozen by the client and rechecked while holding the
    # company lock; stale counts cannot silently overwrite intervening receipts.
    current = position(profile.item_id, data["location_id"])["quantity"]
    if decimal(data["expected_quantity"], "expected_quantity") != current:
        raise BusinessRuleViolation("Stock changed after this count began. Recount before posting.")
    if current + qty < 0:
        raise BusinessRuleViolation("The adjustment would make location stock negative.")
    value = (
        money(data.get("base_value", "0"), company.base_currency, signed=valuation)
        if qty > 0 or valuation
        else issue_cost(profile.item_id, -qty, company.base_currency)
    )
    if qty > 0 and value <= 0:
        raise ValidationError({"base_value": "Value an increase using documented cost."})
    if valuation and (
        qty
        or not original
        or not value
        or current <= 0
        or position(profile.item_id)["value"] + value < 0
    ):
        raise BusinessRuleViolation(
            "Correct a retained stock event with zero quantity and a supported signed cost delta. "
            "The company pool cannot become negative. Supplier consideration changes use "
            "the acquisition correction workflow."
        )
    account = _get(Account, data["offset_account_id"])
    if (
        account.control
        or account.account_type != "expense"
        or not account.is_active
        or not account.is_postable
    ):
        raise ValidationError(
            {"offset_account_id": "Choose an active inventory adjustment expense account."}
        )
    signed_value = value if qty > 0 or valuation else -value
    raw = []
    if value:
        raw = [
            {
                "account_id": control("inventory").pk,
                "currency": company.base_currency,
                "debit" if signed_value > 0 else "credit": str(abs(signed_value)),
            },
            {
                "account_id": account.pk,
                "currency": company.base_currency,
                "credit" if signed_value > 0 else "debit": str(abs(signed_value)),
            },
        ]
    journal = (
        post_journal(
            actor=request.user,
            authority=authorize(request.user, "stock_movement", "post"),
            source_type="stock_movement",
            source_id=key,
            source_action="post",
            posting_key=key,
            request_context=request,
            posting_date=data["date"],
            description=data["reason"],
            lines=raw,
        )
        if raw
        else None
    )
    return _persist(
        request,
        item_id=profile.item_id,
        location_id=data["location_id"],
        on=data["date"],
        kind="price_adjustment" if valuation else "count",
        qty=qty,
        value=signed_value,
        key=key,
        source_type="stock_movement",
        source_id=key,
        reason=data["reason"],
        digest=digest,
        journal=journal,
        original=original,
    )


@transaction.atomic
def transfer(request, data):
    require(request.user, "inventory.manage", "finance.view")
    company = lock_company()
    enabled()
    qty = decimal(data["quantity"], "quantity")
    digest = fingerprint(data)
    key = data["key"]
    if previous := _replay(key + ":out", digest):
        return previous
    if data["from_location_id"] == data["to_location_id"] or qty <= 0:
        raise ValidationError(
            {"quantity": "Choose two different locations and a positive quantity."}
        )
    for location in (data["from_location_id"], data["to_location_id"]):
        _validate(data["item_id"], location, data["date"], qty)
    if position(data["item_id"], data["from_location_id"])["quantity"] < qty:
        raise BusinessRuleViolation("The source location has insufficient stock.")
    value = issue_cost(data["item_id"], qty, company.base_currency)
    outgoing = _persist(
        request,
        item_id=data["item_id"],
        location_id=data["from_location_id"],
        on=data["date"],
        kind="transfer_out",
        qty=-qty,
        value=-value,
        key=key + ":out",
        source_type="stock_transfer",
        source_id=key,
        reason=data["reason"],
        digest=digest,
    )
    _persist(
        request,
        item_id=data["item_id"],
        location_id=data["to_location_id"],
        on=data["date"],
        kind="transfer_in",
        qty=qty,
        value=value,
        key=key + ":in",
        source_type="stock_transfer",
        source_id=key,
        reason=data["reason"],
        digest=digest,
        original=outgoing,
    )
    return outgoing


@transaction.atomic
def reconciliation(on=None):
    company = lock_company()
    qs = Movement.objects.all()
    lines = JournalLine.objects.filter(journal__status="posted", account__control="inventory")
    if on:
        qs = qs.filter(date__lte=on)
        lines = lines.filter(journal__posting_date__lte=on)
    stock = qs.aggregate(value=Sum("base_value"))["value"] or ZERO
    total = lines.aggregate(debit=Sum("base_debit"), credit=Sum("base_credit"))
    gl = (total["debit"] or ZERO) - (total["credit"] or ZERO)
    return {
        "currency": company.base_currency,
        "stock_value": stock,
        "gl_value": gl,
        "difference": stock - gl,
        "date": on,
    }


@transaction.atomic
def overview():
    """Coherent current snapshot; different units never form one quantity."""
    from zoneinfo import ZoneInfo

    from django.db.models import DecimalField, F, Value
    from django.db.models.functions import Coalesce
    from django.utils import timezone

    company = lock_company()
    current = timezone.localdate(timezone=ZoneInfo(company.time_zone))
    tracked = ItemProfile.objects.filter(kind="stock")
    profiles = tracked.annotate(
        on_hand=Coalesce(
            Sum("item__stock_moves__quantity"),
            Value(ZERO),
            output_field=DecimalField(max_digits=30, decimal_places=6),
        ),
        stock_value=Coalesce(
            Sum("item__stock_moves__base_value"),
            Value(ZERO),
            output_field=DecimalField(max_digits=30, decimal_places=6),
        ),
    )
    low = profiles.filter(item__is_active=True, on_hand__lte=F("reorder_level"))
    units = tracked.values("unit__code").annotate(quantity=Sum("item__stock_moves__quantity"))
    return strings(
        {
            "base_currency": company.base_currency,
            "as_of": current,
            "stock_value": Movement.objects.aggregate(v=Sum("base_value"))["v"] or ZERO,
            "tracked_items": tracked.filter(item__is_active=True).count(),
            "nonstock_items": ItemProfile.objects.filter(
                kind="nonstock", item__is_active=True
            ).count(),
            "unit_totals": [
                {"unit": row["unit__code"], "quantity": row["quantity"] or ZERO}
                for row in units.order_by("unit__code")
            ],
            "low_stock_count": low.count(),
            "low_stock": [
                {
                    "id": row["item_id"],
                    "code": row["item__code"],
                    "name": row["item__name"],
                    "quantity": row["on_hand"],
                    "unit": row["unit__code"],
                }
                for row in low.order_by("item__code").values(
                    "item_id", "item__code", "item__name", "on_hand", "unit__code"
                )[:5]
            ],
            "locations": Location.objects.filter(is_active=True).count(),
            "movements_this_month": Movement.objects.filter(
                date__gte=current.replace(day=1), date__lte=current
            ).count(),
            "by_item": [
                {"label": row["item__name"], "amount": row["stock_value"]}
                for row in profiles.order_by("-stock_value", "item_id").values(
                    "item__name", "stock_value"
                )[:8]
            ],
        }
    )
