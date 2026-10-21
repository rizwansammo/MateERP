"""Supplier-accepted cancellation of unmatched receipts; no fabricated cash or AP.

Posted/settled bills must use their owning void/correction workflow first. Returns
never silently amend a paid supplier liability. Remaining consideration retains the
original receipt FX; weighted-average stock removal and explicit variance reconcile.
"""

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.accounting.models import Account
from apps.accounting.money import ZERO, decimal, strings
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

from ..models import GoodsReceipt, SupplierReturn
from .costing import effective_value
from .procurement import enabled


def remaining(receipt):
    native, base = effective_value(receipt)
    returned = receipt.returns.aggregate(
        q=Sum("quantity"), n=Sum("native_value"), b=Sum("base_value")
    )
    return (
        receipt.quantity - (returned["q"] or ZERO),
        native - (returned["n"] or ZERO),
        base - (returned["b"] or ZERO),
    )


def _basis(receipt, data):
    company = lock_company()
    if receipt.kind != "goods" or not receipt.movement_id:
        raise BusinessRuleViolation("Return a retained valued goods receipt.")
    if data["date"] < receipt.date:
        raise ValidationError({"date": "The return cannot precede the acquisition."})
    if receipt.bill_matches.exclude(bill_line__bill__status__in=("void", "cancelled")).exists():
        raise BusinessRuleViolation(
            "Resolve draft matches or the owning bill correction before this "
            "supplier cancellation. "
            "A settled/reconciled liability cannot be silently reduced by returning stock."
        )
    qty = decimal(data["quantity"], "quantity")
    stock._validate(receipt.order_line.item_id, data["location_id"], data["date"], qty)
    available, native, base = remaining(receipt)
    if qty <= 0 or qty > available:
        raise ValidationError(
            {"quantity": "Choose a positive quantity within the unreturned receipt."}
        )
    if stock.position(receipt.order_line.item_id, data["location_id"])["quantity"] < qty:
        raise BusinessRuleViolation("The selected location has insufficient stock for this return.")
    native_value = calculation.allocate(
        native, [qty, available - qty], receipt.order_line.order.currency
    )[0]
    base_value = calculation.allocate(base, [qty, available - qty], company.base_currency)[0]
    inventory_value = stock.issue_cost(receipt.order_line.item_id, qty, company.base_currency)
    if not base_value and not inventory_value:
        raise BusinessRuleViolation(
            "Review the monetary precision of this zero-value supplier return."
        )
    variance_account = _get(Account, data["variance_account_id"])
    if (
        variance_account.control
        or variance_account.account_type != "expense"
        or not variance_account.is_active
        or not variance_account.is_postable
    ):
        raise ValidationError(
            {"variance_account_id": "Choose a reviewed purchase-return cost variance account."}
        )
    return strings(
        {
            "quantity": qty,
            "remaining_quantity": available,
            "native_value": native_value,
            "base_value": base_value,
            "inventory_value": inventory_value,
            "variance": inventory_value - base_value,
            "exchange_rate": receipt.exchange_rate,
            "currency": receipt.order_line.order.currency,
            "last_sequence": Movement.objects.filter(item_id=receipt.order_line.item_id)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first(),
            "settlement_treatment": (
                "Supplier accepted cancellation of unmatched GRNI; no AP/cash movement"
            ),
        }
    )


@transaction.atomic
def request_return(request, receipt_id, data):
    require(request.user, "procurement.manage", "inventory.post", "finance.view")
    lock_company()
    enabled()
    stock.enabled()
    digest = stock.fingerprint({"receipt_id": int(receipt_id), **data})
    existing = SupplierReturn.objects.filter(key=data["key"]).first()
    if existing:
        if existing.fingerprint != digest:
            raise BusinessRuleViolation("This supplier-return key conflicts with earlier content.")
        return {"status": "posted", "return_id": existing.pk, "approval_id": existing.approval_id}
    subject = f"supplier-return:{data['key']}"
    pending = ApprovalRequest.objects.filter(
        action="supplier_return.post", subject_key=subject, status="pending"
    ).first()
    if pending:
        if pending.payload["fingerprint"] != digest:
            raise BusinessRuleViolation("This key conflicts with a pending supplier-return review.")
        return {"status": "pending", "return_id": None, "approval_id": pending.pk}
    receipt = _get(GoodsReceipt, receipt_id)
    basis = _basis(receipt, data)
    payload = strings(
        {"receipt_id": receipt.pk, "data": data, "basis": basis, "fingerprint": digest}
    )
    policy = approvals.policy_for_action("supplier_return.post")
    if (
        policy
        and policy.in_force
        and (
            policy.amount_threshold is None
            or max(decimal(basis["base_value"]), decimal(basis["inventory_value"]))
            >= policy.amount_threshold
        )
    ):
        approval = approvals.submit(
            request,
            action="supplier_return.post",
            title=f"Supplier return: {receipt.reference}",
            subject_key=subject,
            reason=data["reason"],
            payload=payload,
        )
        return {"status": "pending", "return_id": None, "approval_id": approval.pk}
    obj = _post(request, payload)
    return {"status": "posted", "return_id": obj.pk, "approval_id": None}


def _post(request, payload, approval=None):
    from apps.sales.api.base import validated

    from ..api.procurement import SupplierReturnInput

    company = lock_company()
    enabled()
    stock.enabled()
    receipt = _get(GoodsReceipt, payload["receipt_id"])
    data = validated(SupplierReturnInput, payload["data"])
    basis = _basis(receipt, data)
    if basis != payload["basis"]:
        raise BusinessRuleViolation(
            "Stock or receipt consideration changed during review; resubmit the supplier return."
        )
    inventory_value = decimal(basis["inventory_value"])
    base_value = decimal(basis["base_value"])
    variance = decimal(basis["variance"], signed=True)
    lines = []
    for account, amount in (
        (stock.control("grni").pk, base_value),
        (stock.control("inventory").pk, -inventory_value),
        (data["variance_account_id"], variance),
    ):
        if amount:
            lines.append(
                {
                    "account_id": account,
                    "currency": company.base_currency,
                    "debit" if amount > 0 else "credit": str(abs(amount)),
                    "dimensions": {"receipt": receipt.pk},
                    "description": data["reason"][:300],
                }
            )
    journal = post_journal(
        actor=request.user,
        authority=authorize(request.user, "supplier_return", "post"),
        source_type="supplier_return",
        source_id=data["key"],
        source_action="post",
        posting_key=data["key"],
        posting_date=data["date"],
        description=f"Supplier accepted return: {data['reference']}",
        lines=lines,
        request_context=request,
    )
    movement = stock._persist(
        request,
        item_id=receipt.order_line.item_id,
        location_id=data["location_id"],
        on=data["date"],
        kind="supplier_return",
        qty=-decimal(basis["quantity"]),
        value=-inventory_value,
        key=f"supplier-return:{data['key']}",
        source_type="supplier_return",
        source_id=data["key"],
        reason=data["reason"],
        digest=payload["fingerprint"],
        journal=journal,
        original=receipt.movement,
    )
    obj = SupplierReturn.objects.create(
        receipt=receipt,
        date=data["date"],
        quantity=basis["quantity"],
        native_value=basis["native_value"],
        base_value=base_value,
        inventory_value=inventory_value,
        variance=variance,
        variance_account_id=data["variance_account_id"],
        basis=basis,
        reference=data["reference"],
        reason=data["reason"],
        key=data["key"],
        fingerprint=payload["fingerprint"],
        movement=movement,
        journal=journal,
        approval=approval,
        created_by=request.user,
    )
    record(
        "procurement.supplier_returned",
        request=request,
        target=obj,
        after=basis,
        reason=data["reason"],
    )
    return obj


def execute(request, approval, approver):
    obj = _post(request, approval.payload, approval)
    return f"supplier_return:{obj.pk}"
