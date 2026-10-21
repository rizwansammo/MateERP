from datetime import date
from types import SimpleNamespace

import pytest
from django.db import DatabaseError, transaction

from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory import services as stock
from apps.purchasing.services import costing, payables, procurement
from apps.purchasing.services.reconciliation import receiving

from .test_stock import order_and_receive

pytestmark = pytest.mark.django_db


def payload(op, **extra):
    return {
        "date": date(2026, 10, 3),
        "new_net_cost": "1200",
        "variance_account_id": op.books.accounts["5100"].pk,
        "reason": "Signed supplier correction: net price is 120 per unit; "
        "consumed share separately recognized",
        "key": "supplier-price-correction-01",
        **extra,
    }


def test_price_variance_splits_retained_stock_and_consumed_cost_then_matches_once(operations):
    op = operations
    _, receipt = order_and_receive(op, "100", "correction-receipt-01")
    stock.adjust(
        op.request,
        {
            "item_id": op.item.pk,
            "location_id": op.location.pk,
            "date": date(2026, 10, 2),
            "quantity": "-4",
            "expected_quantity": "10",
            "offset_account_id": op.books.accounts["5100"].pk,
            "reason": "Four damaged units consumed before supplier price correction",
            "key": "correction-damage-01",
        },
    )
    result = costing.request_correction(op.request, receipt.pk, payload(op))
    obj = receipt.cost_corrections.get()
    assert result["status"] == "posted"
    assert obj.inventory_delta == 120 and obj.consumed_delta == 80
    assert stock.position(op.item.pk)["value"] == 720
    assert receiving()["difference"] == stock.reconciliation()["difference"] == 0
    assert (
        costing.request_correction(op.request, receipt.pk, payload(op))["correction_id"] == obj.pk
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        type(obj).objects.filter(pk=obj.pk).update(native_delta="1")
    bill = payables.save_bill(
        op.request,
        {
            "vendor_id": op.vendor.pk,
            "vendor_reference": "CORRECTED-1200",
            "bill_date": date(2026, 10, 3),
            "due_date": date(2026, 10, 3),
            "currency": "BDT",
            "lines": [
                {
                    "description": "Corrected goods",
                    "quantity": "10",
                    "unit_price": "120",
                    "account_id": op.books.accounts["6100"].pk,
                }
            ],
        },
    )
    procurement.match_bill(
        op.request, bill.lines.get().pk, [{"receipt_id": receipt.pk, "quantity": "10"}]
    )
    payables.post_bill(op.request, bill.pk)
    assert receiving()["unmatched_base"] == receiving()["difference"] == 0
    assert stock.position(op.item.pk)["value"] == 720
    with pytest.raises(BusinessRuleViolation):
        costing.request_correction(
            op.request, receipt.pk, payload(op, key="after-posted-bill-01", new_net_cost="1300")
        )


def test_price_correction_approval_freezes_cost_basis(operations, make_user):
    op = operations
    _, receipt = order_and_receive(op, "100", "correction-approval-01")
    ApprovalPolicy.objects.filter(category="financial_adjustments").update(
        is_required=True, is_active=True
    )
    result = costing.request_correction(op.request, receipt.pk, payload(op))
    assert result["status"] == "pending" and not receipt.cost_corrections.exists()
    reviewer = SimpleNamespace(user=make_user("cost-reviewer", "administrator"), META={})
    decide(
        reviewer,
        result["approval_id"],
        approve=True,
        reason="Supplier evidence and allocation checked",
    )
    obj = receipt.cost_corrections.get()
    assert obj.inventory_delta == 200 and obj.consumed_delta == 0
    assert receiving()["difference"] == stock.reconciliation()["difference"] == 0
