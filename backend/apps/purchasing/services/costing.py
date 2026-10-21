"""Explicit supplier price corrections, with retained cost-flow attribution.

Only wholly unmatched goods receipts may change their acquisition consideration.
Existing receipts/journals stay immutable. The approved delta is recognized in an
open period, split between the retained pool and disclosed consumed-cost variance.
"""

from decimal import Decimal, localcontext

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.accounting.models import Account
from apps.accounting.money import ZERO, convert, decimal, money, strings
from apps.accounting.services.adapters import authorize
from apps.accounting.services.posting import post_journal
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import require
from apps.approvals import services as approvals
from apps.approvals.models import ApprovalRequest
from apps.audit.services import record
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory import services as stock
from apps.inventory.models import Movement
from apps.sales import calculation
from apps.sales.services import _get

from ..models import GoodsReceipt, ReceiptCostCorrection


def effective_value(receipt):
    corrections = receipt.cost_corrections.aggregate(n=Sum("native_delta"), b=Sum("base_delta"))
    return receipt.native_value + (corrections["n"] or ZERO), receipt.base_value + (
        corrections["b"] or ZERO
    )


def _retained_quantity(receipt):
    """Replay only attribution, never rewrite any historical valuation/posting."""
    pool, retained, removed = ZERO, ZERO, {}
    with localcontext() as ctx:
        ctx.prec = 60
        for move in Movement.objects.filter(item_id=receipt.order_line.item_id).order_by(
            "sequence"
        ):
            if move.kind in ("transfer_in", "transfer_out") or move.quantity == 0:
                continue
            if move.kind == "supplier_return":
                raise BusinessRuleViolation(
                    "Resolve the supplier return before changing this acquisition cost."
                )
            if move.quantity < 0:
                take = retained if -move.quantity == pool else retained * -move.quantity / pool
                removed[str(move.pk)] = (take, -move.quantity)
                retained -= take
            elif move.pk == receipt.movement_id:
                retained += move.quantity
            elif move.kind == "return" and str(move.original_id) in removed:
                component, original_qty = removed[str(move.original_id)]
                retained += component * move.quantity / original_qty
            pool += move.quantity
        return max(ZERO, min(receipt.quantity, retained))


def _basis(receipt, data):
    if receipt.kind != "goods" or not receipt.movement_id:
        raise BusinessRuleViolation("This correction requires a valued goods receipt.")
    if receipt.returns.exists():
        raise BusinessRuleViolation(
            "This receipt has supplier returns. Preserve their accepted consideration; "
            "use a separately documented replacement acquisition."
        )
    if receipt.bill_matches.exclude(bill_line__bill__status__in=("void", "cancelled")).exists():
        raise BusinessRuleViolation(
            "Unmatch draft bills before correcting acquisition cost. Posted bill "
            "consideration requires a source-owned credit/correction; "
            "it cannot be overwritten."
        )
    stock._validate(receipt.order_line.item_id, receipt.location_id, data["date"], ZERO)
    native, base = effective_value(receipt)
    target = money(data["new_net_cost"], receipt.order_line.order.currency)
    if target <= 0 or target == native:
        raise ValidationError(
            {
                "new_net_cost": "Enter a changed positive total net acquisition cost, "
                "excluding recoverable tax."
            }
        )
    delta = target - native
    base_delta = convert(delta, receipt.exchange_rate, stock.lock_company().base_currency)
    retained = _retained_quantity(receipt)
    inventory, consumed = calculation.allocate(
        abs(base_delta), [retained, receipt.quantity - retained], stock.lock_company().base_currency
    )
    sign = Decimal(1) if base_delta >= 0 else Decimal(-1)
    account = _get(Account, data["variance_account_id"])
    if (
        account.control
        or account.account_type != "expense"
        or not account.is_active
        or not account.is_postable
    ):
        raise ValidationError(
            {
                "variance_account_id": "Choose the reviewed consumed-cost / "
                "cost-of-sales expense account."
            }
        )
    return strings(
        {
            "old_native": native,
            "old_base": base,
            "native_delta": delta,
            "base_delta": base_delta,
            "inventory_delta": inventory * sign,
            "consumed_delta": consumed * sign,
            "retained_quantity": retained,
            "original_quantity": receipt.quantity,
            "last_sequence": Movement.objects.filter(item_id=receipt.order_line.item_id)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first(),
        }
    )


@transaction.atomic
def request_correction(request, receipt_id, data):
    require(
        request.user, "procurement.manage", "procurement.approve", "inventory.post", "finance.view"
    )
    lock_company()
    stock.enabled()
    digest = stock.fingerprint({"receipt_id": int(receipt_id), **data})
    existing = ReceiptCostCorrection.objects.filter(key=data["key"]).first()
    if existing:
        if existing.fingerprint != digest:
            raise BusinessRuleViolation("The correction key conflicts with existing content.")
        return {"status": "posted", "correction_id": existing.pk, "approval_id": None}
    subject = f"receipt-cost:{data['key']}"
    pending = ApprovalRequest.objects.filter(
        action="receipt_cost.post", subject_key=subject, status="pending"
    ).first()
    if pending:
        if pending.payload["fingerprint"] != digest:
            raise BusinessRuleViolation("The correction key conflicts with a pending review.")
        return {"status": "pending", "correction_id": None, "approval_id": pending.pk}
    receipt = _get(GoodsReceipt, receipt_id)
    frozen = _basis(receipt, data)
    payload = strings(
        {"receipt_id": receipt.pk, "data": data, "basis": frozen, "fingerprint": digest}
    )
    policy = approvals.policy_for_action("receipt_cost.post")
    if (
        policy
        and policy.in_force
        and (
            policy.amount_threshold is None
            or abs(decimal(frozen["base_delta"], signed=True)) >= policy.amount_threshold
        )
    ):
        approval = approvals.submit(
            request,
            action="receipt_cost.post",
            title=f"Acquisition cost correction: {receipt.reference}",
            subject_key=subject,
            reason=data["reason"],
            payload=payload,
        )
        return {"status": "pending", "correction_id": None, "approval_id": approval.pk}
    obj = _post(request, payload)
    return {"status": "posted", "correction_id": obj.pk, "approval_id": None}


def _post(request, payload):
    from apps.sales.api.base import validated

    from ..api.procurement import CostCorrectionInput

    company = lock_company()
    receipt = _get(GoodsReceipt, payload["receipt_id"])
    data = validated(CostCorrectionInput, payload["data"])
    frozen = _basis(receipt, data)
    if frozen != payload["basis"]:
        raise BusinessRuleViolation(
            "Stock or receipt cost changed during review. Withdraw and submit a new correction."
        )
    inv, consumed, base = (
        decimal(frozen[k], signed=True) for k in ("inventory_delta", "consumed_delta", "base_delta")
    )
    raw = []
    for account_id, value in (
        (stock.control("inventory").pk, inv),
        (data["variance_account_id"], consumed),
        (stock.control("grni").pk, -base),
    ):
        if value:
            raw.append(
                {
                    "account_id": account_id,
                    "currency": company.base_currency,
                    "debit" if value > 0 else "credit": str(abs(value)),
                    "description": data["reason"][:300],
                    "dimensions": {"receipt": receipt.pk},
                }
            )
    journal = (
        post_journal(
            actor=request.user,
            authority=authorize(request.user, "receipt_cost", "post"),
            request_context=request,
            source_type="receipt_cost",
            source_id=data["key"],
            source_action="post",
            posting_key=data["key"],
            posting_date=data["date"],
            description=f"Acquisition price correction: {receipt.reference}",
            lines=raw,
        )
        if raw
        else None
    )
    # A nonzero native delta may convert to zero in a low-value base currency.
    if journal is None:
        raise BusinessRuleViolation(
            "The correction has no representable base-currency value; "
            "review the monetary precision explicitly."
        )
    movement = (
        stock._persist(
            request,
            item_id=receipt.order_line.item_id,
            location_id=receipt.location_id,
            on=data["date"],
            kind="price_adjustment",
            qty=ZERO,
            value=inv,
            key=f"price:{data['key']}",
            source_type="receipt_cost",
            source_id=data["key"],
            reason=data["reason"][:500],
            digest=payload["fingerprint"],
            journal=journal,
            original=receipt.movement,
        )
        if inv
        else None
    )
    obj = ReceiptCostCorrection.objects.create(
        receipt=receipt,
        date=data["date"],
        native_delta=frozen["native_delta"],
        base_delta=base,
        inventory_delta=inv,
        consumed_delta=consumed,
        variance_account_id=data["variance_account_id"],
        basis=frozen,
        reason=data["reason"],
        key=data["key"],
        fingerprint=payload["fingerprint"],
        journal=journal,
        movement=movement,
        created_by=request.user,
    )
    record(
        "procurement.acquisition_cost_corrected",
        request=request,
        target=obj,
        after=frozen,
        reason=data["reason"],
    )
    return obj


def execute(request, approval, approver):
    obj = _post(request, approval.payload)
    return f"receipt_cost:{obj.pk}"
