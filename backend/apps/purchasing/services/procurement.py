"""Purchase authority, receiving and exact three-way matching, without a second AP ledger."""

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounting.money import ZERO, convert, decimal, strings
from apps.accounting.services.adapters import authorize
from apps.accounting.services.setup import lock_company, rate_for
from apps.accounts.authorization import get_permission_codes, require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.catalog.models import ItemProfile
from apps.company.services import is_module_enabled
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory import services as stock
from apps.sales import calculation
from apps.sales.models import BillingItem
from apps.sales.services import _get, enabled_currency, next_code

from ..models import (
    GoodsReceipt,
    ProcurementEvidence,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderSnapshot,
    ReceiptBillMatch,
    Vendor,
    VendorBillLine,
)


def enabled():
    if not is_module_enabled("procurement"):
        raise BusinessRuleViolation("Procurement is disabled. Historical orders remain readable.")


def snapshot(order):
    return strings(
        {
            "id": order.pk,
            "number": order.number,
            "revision": order.revision,
            "vendor_id": order.vendor_id,
            "vendor_name": order.vendor.name,
            "date": order.date,
            "currency": order.currency,
            "prices_include_tax": order.prices_include_tax,
            "notes": order.notes,
            "total": order.total,
            "lines": list(
                order.lines.values(
                    "id",
                    "position",
                    "item_id",
                    "description",
                    "quantity",
                    "unit_price",
                    "tax_code_id",
                    "taxable",
                    "tax",
                    "total",
                )
            ),
        }
    )


@transaction.atomic
def save_order(request, data, pk=None):
    require(request.user, "procurement.manage", "finance.view")
    lock_company()
    enabled()
    obj = _get(PurchaseOrder, pk) if pk else PurchaseOrder(created_by=request.user)
    if pk and (obj.status not in ("draft", "rejected") or data.get("revision") != obj.revision):
        raise BusinessRuleViolation("Only current draft/rejected revisions may be edited.")
    for field in ("date", "expected_date", "currency", "prices_include_tax", "notes"):
        if field in data:
            setattr(obj, field, data[field])
    if "vendor_id" in data:
        obj.vendor = _get(Vendor, data["vendor_id"])
    if not obj.vendor_id or not obj.vendor.is_active:
        raise ValidationError({"vendor_id": "Choose an active vendor."})
    obj.currency = obj.currency or obj.vendor.currency
    enabled_currency(obj.currency)
    rows = data.get("lines")
    if not rows:
        raise ValidationError({"lines": "Provide the complete order lines."})
    result = calculation.calculate(
        currency=obj.currency, on=obj.date, lines=rows, prices_include_tax=obj.prices_include_tax
    )
    obj.taxable, obj.tax, obj.total = result["taxable"], result["tax"], result["total"]
    if not pk:
        obj.number = next_code("purchase_order", "PO", PurchaseOrder, "number")
    else:
        obj.revision += 1
    obj.status = "draft"
    obj.full_clean()
    obj.save()
    obj.lines.all().delete()
    for row, calculated in zip(rows, result["lines"], strict=True):
        item = _get(BillingItem, row["item_id"])
        if not item.is_active:
            raise ValidationError({"lines": "Inactive catalog items cannot be ordered."})
        profile = ItemProfile.objects.select_related("unit").filter(item=item).first()
        if profile and not profile.unit.allows_fraction and calculated["quantity"] % 1:
            raise ValidationError({"lines": "This unit requires whole quantities."})
        PurchaseOrderLine.objects.create(
            order=obj,
            item=item,
            description=row.get("description") or item.name,
            **{
                k: calculated[k]
                for k in (
                    "position",
                    "quantity",
                    "unit_price",
                    "tax_code_id",
                    "taxable",
                    "tax",
                    "total",
                )
            },
        )
    record("procurement.order_saved", request=request, target=obj, after=snapshot(obj))
    return obj


@transaction.atomic
def submit_order(request, pk):
    require(request.user, "procurement.manage", "finance.view")
    company = lock_company()
    enabled()
    obj = _get(PurchaseOrder, pk)
    if obj.status != "draft":
        raise BusinessRuleViolation("Submit the current draft only.")
    frozen = snapshot(obj)
    PurchaseOrderSnapshot.objects.create(
        order=obj, revision=obj.revision, snapshot=frozen, actor=request.user
    )
    policy = approvals.policy_for_action("purchase_order.approve")
    fx, _ = rate_for(obj.currency, obj.date, company.base_currency)
    applies = (
        policy
        and policy.in_force
        and (
            policy.amount_threshold is None
            or convert(obj.total, fx, company.base_currency) >= policy.amount_threshold
        )
    )
    if applies:
        obj.approval = approvals.submit(
            request,
            action="purchase_order.approve",
            payload=frozen,
            title=f"Approve {obj.number} — {obj.vendor.name}"[:200],
            subject_key=f"po:{obj.pk}",
        )
        obj.status = "pending"
    else:
        # Absence of a policy does not grant the purchaser approval authority.
        require(request.user, "procurement.approve")
        obj.status, obj.approved_by = "approved", request.user
    obj.save()
    record("procurement.order_submitted", request=request, target=obj, after={"status": obj.status})
    return obj


def execute_approval(request, approval, approver):
    obj = _get(PurchaseOrder, approval.payload["id"])
    if obj.status != "pending" or snapshot(obj) != approval.payload:
        raise BusinessRuleViolation("The frozen purchase order has changed.")
    obj.status, obj.approved_by = "approved", approver
    obj.save(update_fields=["status", "approved_by"])
    record("procurement.order_approved", request=request, target=obj)
    return f"purchase_order:{obj.pk}"


def declined(request, approval):
    obj = _get(PurchaseOrder, approval.payload["id"])
    obj.status = "rejected"
    obj.save(update_fields=["status"])


@transaction.atomic
def transition(request, pk, action, reason=""):
    require(request.user, "procurement.manage", "finance.view")
    lock_company()
    obj = _get(PurchaseOrder, pk)
    if action == "issue" and obj.status == "approved":
        enabled()
        obj.status, obj.issued_at = "issued", timezone.now()
    elif action == "cancel" and obj.status in (
        "draft",
        "approved",
        "issued",
        "partial",
        "rejected",
    ):
        if not reason.strip():
            raise ValidationError({"reason": "Explain cancellation of the remaining commitment."})
        obj.status, obj.closing_reason = "cancelled", reason
    elif action == "close" and obj.status in ("received", "partial"):
        require(request.user, "procurement.approve")
        if not reason.strip():
            raise ValidationError({"reason": "Explain closure and any unfulfilled remainder."})
        for receipt in GoodsReceipt.objects.filter(order_line__order=obj):
            matched = (
                receipt.bill_matches.filter(
                    bill_line__bill__status__in=("posted", "partially_paid", "paid")
                ).aggregate(q=Sum("quantity"))["q"]
                or ZERO
            )
            if matched != receipt.quantity:
                raise BusinessRuleViolation(
                    "Clear all accepted receipts against posted bills before closing."
                )
        obj.status, obj.closing_reason = "closed", reason
    else:
        raise BusinessRuleViolation("This transition is not available in the current state.")
    obj.save()
    record(f"procurement.order_{action}", request=request, target=obj, reason=reason)
    return obj


@transaction.atomic
def receive(request, data):
    require(request.user, "procurement.manage", "finance.view")
    company = lock_company()
    enabled()
    digest = stock.fingerprint(data)
    previous = GoodsReceipt.objects.filter(key=data["key"]).first()
    if previous:
        if previous.fingerprint != digest:
            raise BusinessRuleViolation("Receipt key conflicts with earlier content.")
        return previous
    line = _get(PurchaseOrderLine, data["order_line_id"])
    order = _get(PurchaseOrder, line.order_id)
    if order.status not in ("issued", "partial"):
        raise BusinessRuleViolation("Receive against an issued purchase order.")
    qty = decimal(data["quantity"], "quantity")
    rejected = decimal(data.get("rejected_quantity", "0"), "rejected_quantity")
    received = line.receipts.aggregate(q=Sum("quantity"))["q"] or ZERO
    if qty <= 0 or received + qty > line.quantity:
        raise BusinessRuleViolation(
            "Accepted quantities cannot exceed the authorized order. "
            "Amend the commitment explicitly."
        )
    profile = ItemProfile.objects.select_related("unit").filter(item=line.item).first()
    if profile and not profile.unit.allows_fraction and (qty % 1 or rejected % 1):
        raise ValidationError({"quantity": "This unit requires whole quantities."})
    # Allocate the frozen net cost; the final receipt takes the exact remainder.
    native = (
        line.taxable - (line.receipts.aggregate(v=Sum("native_value"))["v"] or ZERO)
        if received + qty == line.quantity
        else calculation.allocate(line.taxable, [qty, line.quantity - qty], order.currency)[0]
    )
    fx, _ = rate_for(order.currency, data["date"], company.base_currency)
    value = convert(native, fx, company.base_currency)
    kind = "goods" if profile and profile.kind == "stock" else "service"
    movement = None
    if kind == "goods":
        if not data.get("location_id"):
            raise ValidationError({"location_id": "Choose the receiving warehouse."})
        movement = stock.receive(
            request,
            item_id=line.item_id,
            location_id=data["location_id"],
            on=data["date"],
            qty=qty,
            value=value,
            key=f"receipt:{data['key']}:stock",
            source_type="goods_receipt",
            source_id=digest,
            authority=authorize(request.user, "goods_receipt", "receive"),
            reason=data["reason"],
        )
    obj = GoodsReceipt.objects.create(
        order_line=line,
        date=data["date"],
        quantity=qty,
        rejected_quantity=rejected,
        kind=kind,
        location_id=data.get("location_id"),
        reference=data["reference"],
        reason=data["reason"],
        movement=movement,
        native_value=native,
        base_value=value,
        exchange_rate=fx,
        key=data["key"],
        fingerprint=digest,
        created_by=request.user,
    )
    done = all(
        (row.receipts.aggregate(q=Sum("quantity"))["q"] or ZERO) == row.quantity
        for row in order.lines.all()
    )
    order.status = "received" if done else "partial"
    order.save(update_fields=["status"])
    record(
        "procurement.receipt_accepted",
        request=request,
        target=obj,
        after={"quantity": qty, "rejected_quantity": rejected, "kind": obj.kind},
    )
    return obj


@transaction.atomic
def match_bill(request, bill_line_id, rows):
    require(request.user, "bills.manage", "procurement.manage", "finance.view")
    lock_company()
    bill_line = _get(VendorBillLine, bill_line_id)
    if bill_line.bill.status != "draft":
        raise BusinessRuleViolation("Match only an editable bill draft.")
    bill_line.receipt_matches.all().delete()
    if not rows:
        return []
    if len({r["receipt_id"] for r in rows}) != len(rows):
        raise ValidationError({"receipts": "Each receipt must occur once per bill line."})
    matches = []
    for row in rows:
        receipt = _get(GoodsReceipt, row["receipt_id"])
        order = receipt.order_line.order
        if order.vendor_id != bill_line.bill.vendor_id or order.currency != bill_line.bill.currency:
            raise BusinessRuleViolation("Match the same vendor and transaction currency.")
        qty = decimal(row["quantity"], "quantity")
        used = (
            receipt.bill_matches.exclude(
                bill_line__bill__status__in=("void", "cancelled")
            ).aggregate(q=Sum("quantity"))["q"]
            or ZERO
        )
        from .returns import remaining

        available, receipt_native, receipt_base = remaining(receipt)
        if qty <= 0 or used + qty > available:
            raise BusinessRuleViolation("Receipt quantity has already been matched or is exceeded.")
        others = receipt.bill_matches.exclude(bill_line__bill__status__in=("void", "cancelled"))
        if used + qty == available:
            native = receipt_native - (others.aggregate(v=Sum("native_value"))["v"] or ZERO)
            base = receipt_base - (others.aggregate(v=Sum("base_value"))["v"] or ZERO)
        else:
            native = calculation.allocate(receipt_native, [qty, available - qty], order.currency)[0]
            base = calculation.allocate(receipt_base, [qty, available - qty], company_base())[0]
        match = ReceiptBillMatch.objects.create(
            receipt=receipt,
            bill_line=bill_line,
            quantity=qty,
            native_value=native,
            base_value=base,
            created_by=request.user,
        )
        matches.append(match)
    if (
        sum((m.quantity for m in matches), ZERO) != bill_line.quantity
        or sum((m.native_value for m in matches), ZERO) != bill_line.taxable
    ):
        raise BusinessRuleViolation(
            "Exact matching requires bill quantity and net cost to equal selected receipts. "
            "Review differences explicitly."
        )
    record(
        "procurement.bill_matched",
        request=request,
        target=bill_line,
        after={"receipt_ids": [m.receipt_id for m in matches]},
    )
    return matches


def company_base():
    from apps.billing.services.common import base_currency

    return base_currency()


@transaction.atomic
def amend_order(request, pk, data, reason):
    require(request.user, "procurement.manage", "procurement.approve", "finance.view")
    lock_company()
    enabled()
    original = _get(PurchaseOrder, pk)
    if original.status not in ("approved", "issued", "partial") or not reason.strip():
        raise BusinessRuleViolation("Amend an approved open commitment with an explicit reason.")
    if data["vendor_id"] != original.vendor_id or data["currency"] != original.currency:
        raise BusinessRuleViolation(
            "An amendment retains vendor and currency. Use another order for a different party."
        )
    replacement = save_order(request, data)
    replacement.revised_from = original
    replacement.save(update_fields=["revised_from"])
    original.status = "cancelled"
    original.closing_reason = f"Remainder superseded by {replacement.number}: {reason}"[:500]
    original.save(update_fields=["status", "closing_reason"])
    record(
        "procurement.order_amended",
        request=request,
        target=original,
        after={"replacement": replacement.pk, "status": original.status},
        reason=reason,
    )
    # The replacement needs a new frozen review/issue. Earlier receipts and their
    # cost/matching history stay on the original order.
    return replacement


def can_read_evidence(user, stored):
    return {"finance.view", "documents.vendor.view"} <= get_permission_codes(
        user
    ) and ProcurementEvidence.objects.filter(file=stored).exists()


@transaction.atomic
def add_evidence(request, order_id, data, upload):
    require(request.user, "finance.view", "procurement.manage", "documents.manage")
    lock_company()
    order = _get(PurchaseOrder, order_id)
    receipt = _get(GoodsReceipt, data["receipt_id"]) if data.get("receipt_id") else None
    if receipt and receipt.order_line.order_id != order.pk:
        raise ValidationError({"receipt_id": "The receipt belongs to another order."})
    from apps.files.services import store_document

    stored = store_document(upload, purpose="procurement_evidence", user=request.user)
    obj = ProcurementEvidence.objects.create(
        order=order,
        receipt=receipt,
        file=stored,
        description=data["description"],
        created_by=request.user,
    )
    record(
        "procurement.evidence_added",
        request=request,
        target=obj,
        after={"order": order.pk, "receipt": receipt.pk if receipt else None, "file": stored.pk},
    )
    return obj


def matched_bill_debits(bill, fx, base):
    """Historical GRNI clears once; transaction-date AP and input tax remain explicit.

    Called only inside the existing vendor-bill posting transaction. Exact
    matching blocks unsupported price differences instead of hiding a plug.
    """
    from .payables import _debits

    rows, matched = [], []
    for line in bill.lines.select_related("tax_revision"):
        matches = list(line.receipt_matches.select_related("receipt__order_line__order"))
        if not matches:
            rows.append((line.account_id, line.tax_revision, line.taxable, line.tax))
            continue
        if (
            sum((m.quantity for m in matches), ZERO) != line.quantity
            or sum((m.native_value for m in matches), ZERO) != line.taxable
        ):
            raise BusinessRuleViolation("Bill lines no longer equal their receipt matches.")
        for match in matches:
            receipt = match.receipt
            if (
                receipt.order_line.order.vendor_id != bill.vendor_id
                or receipt.order_line.order.currency != bill.currency
            ):
                raise BusinessRuleViolation("The receipt no longer matches this vendor/currency.")
            reserved = (
                receipt.bill_matches.exclude(
                    bill_line__bill__status__in=("void", "cancelled")
                ).aggregate(q=Sum("quantity"))["q"]
                or ZERO
            )
            if reserved > receipt.quantity:
                raise BusinessRuleViolation("Receipt matching exceeds its accepted quantity.")
        goods = [m for m in matches if m.receipt.kind == "goods"]
        if goods and len(goods) != len(matches):
            raise BusinessRuleViolation("A bill line cannot combine stock and service acceptance.")
        if goods:
            matched.extend(goods)
            rows.append((line.account_id, line.tax_revision, ZERO, line.tax))
        else:
            rows.append((line.account_id, line.tax_revision, line.taxable, line.tax))
    _, raw = (
        _debits(rows, bill.currency, fx, base) if any(r[2] or r[3] for r in rows) else (ZERO, [])
    )
    for match in matched:
        raw.append(
            {
                "account_id": stock.control("grni").pk,
                "currency": base,
                "debit": str(match.base_value),
                "description": f"Clear receipt {match.receipt_id}",
                "dimensions": {"receipt": match.receipt_id, "bill": bill.pk},
            }
        )
    base_total = convert(bill.total, fx, base)
    debits = sum((decimal(r.get("base_debit", r["debit"])) for r in raw), ZERO)
    difference = base_total - debits
    if difference:
        raw.append(
            {
                "account_id": stock.control("fx_loss" if difference > 0 else "fx_gain").pk,
                "currency": base,
                "debit" if difference > 0 else "credit": str(abs(difference)),
                "description": "Historical GRNI / bill-rate exchange difference",
            }
        )
    return base_total, raw
