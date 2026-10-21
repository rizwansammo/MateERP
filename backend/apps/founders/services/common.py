"""Shared identity, exact allocation and authorization boundaries."""

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounting.money import ZERO, decimal, money, quantum
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import get_permission_codes, require
from apps.audit.services import record
from apps.company.models import FinancialParty
from apps.company.services import is_module_enabled
from apps.core.exceptions import BusinessRuleViolation


def enabled(module="founder"):
    if not is_module_enabled(module):
        raise BusinessRuleViolation(
            "This module is disabled. Historical data is retained.", code="module_disabled"
        )


def on_date(value, field="date"):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ValidationError({field: "Use a valid ISO date."}) from None


def party(pk, *, on=None, founder=False):
    obj = FinancialParty.objects.filter(pk=pk).first()
    if obj is None:
        raise ValidationError({"party_id": "Select a participant."})
    if on and (not obj.is_active or obj.joined > on or (obj.left and obj.left < on)):
        raise BusinessRuleViolation("The participant is not active on this date.")
    if founder and not obj.is_founder:
        raise ValidationError({"party_id": "Select a founder."})
    return obj


def positive(value, currency):
    result = money(value, currency)
    if result <= ZERO:
        raise ValidationError({"amount": "Enter a positive amount."})
    return result


def total(qs, field="amount"):
    return qs.aggregate(value=Sum(field))["value"] or ZERO


def exact_weights(raw, *, percentages=False):
    if not isinstance(raw, dict) or not raw or len(raw) > 100:
        raise ValidationError({"weights": "Select between 1 and 100 participants."})
    values = {}
    for key, value in raw.items():
        try:
            key = str(int(key))
        except (ValueError, TypeError):
            raise ValidationError({"weights": "Invalid participant."}) from None
        val = decimal(value)
        if val <= ZERO:
            raise ValidationError({"weights": "Every participant needs a positive weight."})
        values[key] = val
    if percentages and sum(values.values(), ZERO) != Decimal("100"):
        raise ValidationError({"weights": "Custom percentages must total exactly 100."})
    return values


def split(amount, currency, weights):
    """Largest remainder in native minor units, with stable party-ID tie breaking."""
    values = exact_weights(weights)
    units = int(money(amount, currency) / quantum(currency))
    scale = max(0, max(-v.as_tuple().exponent for v in values.values()))
    ints = {k: int(v * 10**scale) for k, v in values.items()}
    denominator = sum(ints.values())
    parts = {k: divmod(units * v, denominator) for k, v in ints.items()}
    counts = {k: v[0] for k, v in parts.items()}
    for key in sorted(parts, key=lambda k: (-parts[k][1], int(k)))[: units - sum(counts.values())]:
        counts[key] += 1
    return {k: Decimal(v) * quantum(currency) for k, v in counts.items()}


@transaction.atomic
def save_party(request, data, pk=None):
    codes = get_permission_codes(request.user)
    if not {"founder.transactions.manage", "ownership.manage"} & codes:
        raise PermissionDenied()
    lock_company()
    obj = (
        FinancialParty.objects.select_for_update().filter(pk=pk).first() if pk else FinancialParty()
    )
    if obj is None:
        raise NotFound()
    fields = {
        "name",
        "display_name",
        "kind",
        "email",
        "phone",
        "country",
        "notes",
        "user_id",
        "is_founder",
        "is_shareholder",
        "is_partner",
        "is_active",
        "joined",
        "left",
    }
    before = {key: str(getattr(obj, key)) for key in fields} if pk else {}
    # Linking identities is an access-control change, not an ordinary name edit.
    if data.get("user_id") != obj.user_id and "user_id" in data:
        require(request.user, "users.manage")
    for key in fields & data.keys():
        setattr(obj, key, data[key])
    obj.full_clean()
    obj.save()
    record(
        "founder.party_updated" if pk else "founder.party_created",
        request=request,
        target=obj,
        before=before,
        after={k: str(getattr(obj, k)) for k in fields},
    )
    return obj
