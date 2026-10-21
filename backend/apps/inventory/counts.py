"""Count review freezes both physical expectation and cost-pool provenance."""

from django.db import transaction
from django.db.models import Max

from apps.accounting.money import decimal, strings
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.core.exceptions import BusinessRuleViolation
from apps.sales.services import _get

from . import services as stock
from .models import Movement, StockCount


def basis(data):
    return strings(
        {
            "pool": stock.position(data["item_id"]),
            "location": stock.position(data["item_id"], data["location_id"])["quantity"],
            "sequence": Movement.objects.filter(item_id=data["item_id"]).aggregate(
                s=Max("sequence")
            )["s"]
            or 0,
        }
    )


@transaction.atomic
def submit(request, data):
    require(request.user, "finance.view", "inventory.manage", "inventory.post")
    company = lock_company()
    stock.enabled()
    digest = stock.fingerprint(data)
    previous = StockCount.objects.filter(key=data["key"]).first()
    if previous:
        if previous.fingerprint != digest:
            raise BusinessRuleViolation("The count key belongs to different content.")
        return previous
    qty = decimal(data["quantity"], signed=True)
    valuation = data.get("kind") == "valuation"
    if valuation:
        require(request.user, "accounting.manage")
    stock._validate(data["item_id"], data["location_id"], data["date"], qty)
    frozen = basis(data)
    if decimal(frozen["location"]) != decimal(data["expected_quantity"]):
        raise BusinessRuleViolation("Stock changed; recount before submitting.")
    value = (
        stock.money(data.get("base_value", "0"), company.base_currency, signed=valuation)
        if qty > 0 or valuation
        else stock.issue_cost(data["item_id"], -qty, company.base_currency)
    )
    if valuation:
        if qty or not value or not data.get("correction_of_id"):
            raise BusinessRuleViolation(
                "A valuation correction needs zero quantity, a signed cost delta "
                "and original event."
            )
        original = _get(Movement, data["correction_of_id"])
        if (
            original.item_id != data["item_id"]
            or original.date > data["date"]
            or decimal(frozen["location"]) <= 0
            or decimal(frozen["pool"]["value"]) + value < 0
        ):
            raise BusinessRuleViolation(
                "Choose an earlier event for this product and a supported nonnegative cost pool."
            )
    elif not qty or decimal(frozen["location"]) + qty < 0 or (qty > 0 and value <= 0):
        raise BusinessRuleViolation(
            "Enter a nonzero, supported count variance and documented value."
        )
    obj = StockCount.objects.create(
        payload=strings(data),
        basis=frozen,
        key=data["key"],
        fingerprint=digest,
        created_by=request.user,
    )
    policy = approvals.policy_for_action("stock_count.post")
    if (
        policy
        and policy.in_force
        and (policy.amount_threshold is None or abs(value) >= policy.amount_threshold)
    ):
        obj.approval = approvals.submit(
            request,
            action="stock_count.post",
            subject_key=f"stock-count:{obj.pk}",
            title=f"Review stock count {obj.pk}",
            reason=data["reason"],
            payload={"count_id": obj.pk},
        )
        obj.save(update_fields=["approval"])
    else:
        _post(request, obj)
    record(
        "inventory.count_submitted",
        request=request,
        target=obj,
        after={"status": obj.status, "basis": frozen},
        reason=data["reason"],
    )
    return obj


def _post(request, obj):
    from apps.sales.api.base import validated

    from .api.serializers import AdjustmentInput

    data = validated(AdjustmentInput, obj.payload)
    if obj.status != "pending" or basis(data) != obj.basis:
        raise BusinessRuleViolation(
            "This count is stale or already decided. Withdraw it and recount; "
            "stock/value changed after submission."
        )
    obj.movement = stock.adjust(request, data, reviewed_count=obj)
    obj.status = "posted"
    obj.save(update_fields=["movement", "status"])


def execute(request, approval, approver):
    obj = _get(StockCount, approval.payload["count_id"])
    _post(request, obj)
    record("inventory.count_posted", request=request, target=obj)
    return f"stock_count:{obj.pk}"


def declined(request, approval):
    obj = _get(StockCount, approval.payload["count_id"])
    obj.status = "rejected"
    obj.save(update_fields=["status"])
