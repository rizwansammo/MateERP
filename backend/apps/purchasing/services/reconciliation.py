"""Accounts payable subledger reconciled to the payable control account."""

from django.db.models import F, Sum

from apps.accounting.money import ZERO
from apps.billing.services.reconciliation import gl_balance

from ..models import Expense, VendorBill

POSTED = ("posted", "partially_paid", "paid")


def receiving():
    from ..models import GoodsReceipt, ReceiptBillMatch, ReceiptCostCorrection, SupplierReturn

    received = GoodsReceipt.objects.filter(kind="goods").aggregate(v=Sum("base_value"))["v"] or ZERO
    corrected = ReceiptCostCorrection.objects.aggregate(v=Sum("base_delta"))["v"] or ZERO
    returned = SupplierReturn.objects.aggregate(v=Sum("base_value"))["v"] or ZERO
    matched = (
        ReceiptBillMatch.objects.filter(
            receipt__kind="goods", bill_line__bill__status__in=POSTED
        ).aggregate(v=Sum("base_value"))["v"]
        or ZERO
    )
    _, ledger = gl_balance("grni", credit_normal=True)
    return {
        "received_base": received,
        "corrections_base": corrected,
        "returned_base": returned,
        "matched_base": matched,
        "unmatched_base": received + corrected - returned - matched,
        "ledger": ledger,
        "difference": ledger - (received + corrected - returned - matched),
    }


def payables():
    bills = VendorBill.objects.filter(status__in=POSTED).aggregate(
        t=Sum("base_total"), s=Sum("base_settled")
    )
    accrued = Expense.objects.filter(payment_mode="accrued", status__in=POSTED).aggregate(
        t=Sum("base_total"), s=Sum("base_settled")
    )
    subledger = (
        (bills["t"] or ZERO)
        - (bills["s"] or ZERO)
        + (accrued["t"] or ZERO)
        - (accrued["s"] or ZERO)
    )
    account, ledger = gl_balance("payable", credit_normal=True)
    return {
        "account": account,
        "subledger": subledger,
        "ledger": ledger,
        "difference": ledger - subledger,
    }


def vendor_balances(vendor_ids=None):
    """Open native balances per vendor and currency (bills plus accrued expenses)."""
    out = {}
    for model, filters in ((VendorBill, {}), (Expense, {"payment_mode": "accrued"})):
        qs = model.objects.filter(status__in=("posted", "partially_paid"), **filters)
        if vendor_ids is not None:
            qs = qs.filter(vendor_id__in=vendor_ids)
        rows = (
            qs.values("vendor_id", "currency")
            .annotate(open=Sum(F("total") - F("amount_paid")))
            .order_by()
        )
        for row in rows:
            current = out.setdefault(row["vendor_id"], {}).get(row["currency"], ZERO)
            out[row["vendor_id"]][row["currency"]] = current + row["open"]
    return out
