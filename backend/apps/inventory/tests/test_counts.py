from types import SimpleNamespace

import pytest
from django.db import DatabaseError, transaction
from rest_framework.exceptions import PermissionDenied

from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory import counts
from apps.inventory import services as stock
from apps.inventory.models import Movement, StockCount

from .test_stock import order_and_receive

pytestmark = pytest.mark.django_db


def count_data(op, key="retained-count-01"):
    return {
        "item_id": op.item.pk,
        "location_id": op.location.pk,
        "date": op.on,
        "quantity": "-2",
        "expected_quantity": "10",
        "offset_account_id": op.books.accounts["5100"].pk,
        "reason": "Signed physical count: two damaged units",
        "key": key,
    }


def test_retained_count_and_exact_retry(operations, admin_client):
    op = operations
    order_and_receive(op, "100", "stock-count-receipt-01")
    payload = count_data(op)
    result = admin_client.post("/api/v1/inventory/adjustments/", payload, format="json")
    assert result.status_code == 201, result.data
    assert result.data["status"] == "posted"
    assert stock.position(op.item.pk)["quantity"] == 8
    assert counts.submit(op.request, payload).pk == result.data["id"]
    assert StockCount.objects.count() == 1
    assert stock.reconciliation()["difference"] == 0
    with pytest.raises(DatabaseError), transaction.atomic():
        StockCount.objects.filter(pk=result.data["id"]).update(payload={})


def test_count_approval_freezes_basis_and_blocks_stale_review(operations, make_user):
    op = operations
    order_and_receive(op, "100", "count-approval-receipt")
    ApprovalPolicy.objects.filter(category="financial_adjustments").update(
        is_required=True, is_active=True
    )
    obj = counts.submit(op.request, count_data(op))
    assert obj.status == "pending" and obj.movement_id is None
    assert stock.position(op.item.pk)["quantity"] == 10
    with pytest.raises(BusinessRuleViolation):
        stock.adjust(op.request, count_data(op))
    with pytest.raises(PermissionDenied):
        decide(op.request, obj.approval_id, approve=True)
    other = stock.save_location(op.request, {"code": "COUNT-OTHER", "name": "Second"})
    stock.transfer(
        op.request,
        {
            "item_id": op.item.pk,
            "date": op.on,
            "from_location_id": op.location.pk,
            "to_location_id": other.pk,
            "quantity": "1",
            "reason": "Intervening transfer",
            "key": "count-stale-transfer",
        },
    )
    reviewer = SimpleNamespace(user=make_user("counter-reviewer", "administrator"), META={})
    with pytest.raises(BusinessRuleViolation):
        decide(reviewer, obj.approval_id, approve=True)
    assert not Movement.objects.filter(kind="count").exists()
    decide(
        reviewer, obj.approval_id, approve=False, reason="Recount after intervening stock change"
    )
    obj.refresh_from_db()
    assert obj.status == "rejected"


def test_count_independent_approval_posts_once(operations, make_user):
    op = operations
    order_and_receive(op, "100", "count-review-receipt")
    ApprovalPolicy.objects.filter(category="financial_adjustments").update(
        is_required=True, is_active=True
    )
    obj = counts.submit(op.request, count_data(op))
    reviewer = SimpleNamespace(user=make_user("counter-approver", "administrator"), META={})
    decide(reviewer, obj.approval_id, approve=True, reason="Inspected counted quantity")
    obj.refresh_from_db()
    assert obj.status == "posted" and obj.movement.base_value == -200
    assert stock.reconciliation()["difference"] == 0


def test_cost_only_correction_preserves_quantity_and_original_event(operations, admin_client):
    op = operations
    _, receipt = order_and_receive(op, "100", "valuation-correction-receipt")
    payload = {
        "item_id": op.item.pk,
        "location_id": op.location.pk,
        "date": op.on,
        "quantity": "0",
        "expected_quantity": "10",
        "base_value": "-125.50",
        "kind": "valuation",
        "correction_of_id": str(receipt.movement_id),
        "offset_account_id": op.books.accounts["5100"].pk,
        "reason": "Documented damaged acquisition cost impairment; original event retained",
        "key": "valuation-correction-01",
    }
    response = admin_client.post("/api/v1/inventory/adjustments/", payload, format="json")
    assert response.status_code == 201, response.data
    move = Movement.objects.get(pk=response.data["movement_id"])
    assert move.quantity == 0 and move.base_value == stock.decimal("-125.50", signed=True)
    assert move.original_id == receipt.movement_id
    assert stock.position(op.item.pk)["quantity"] == 10
    assert stock.position(op.item.pk)["value"] == stock.decimal("874.50")
    assert stock.reconciliation()["difference"] == 0
    assert counts.submit(op.request, {**payload, "date": op.on}).pk == response.data["id"]
    with pytest.raises(BusinessRuleViolation):
        counts.submit(
            op.request, {**payload, "base_value": "-900", "key": "unsupported-valuation-01"}
        )


def test_cost_correction_requires_accounting_authority_and_independent_policy(
    operations, make_user, client_for, user_with
):
    op = operations
    _, receipt = order_and_receive(op, "100", "valuation-approval-receipt")
    payload = {
        "item_id": op.item.pk,
        "location_id": op.location.pk,
        "date": op.on,
        "quantity": "0",
        "expected_quantity": "10",
        "base_value": "-50",
        "kind": "valuation",
        "correction_of_id": str(receipt.movement_id),
        "offset_account_id": op.books.accounts["5100"].pk,
        "reason": "Reviewed cost impairment",
        "key": "valuation-reviewed-01",
    }
    restricted = client_for(
        user_with("stock-not-accountant", "inventory.manage", "inventory.post", "finance.view")
    )
    assert (
        restricted.post("/api/v1/inventory/adjustments/", payload, format="json").status_code == 403
    )
    ApprovalPolicy.objects.filter(category="financial_adjustments").update(
        is_required=True, is_active=True
    )
    count = counts.submit(op.request, payload)
    assert count.status == "pending" and stock.position(op.item.pk)["value"] == 1000
    with pytest.raises(PermissionDenied):
        decide(op.request, count.approval_id, approve=True)
    reviewer = SimpleNamespace(user=make_user("valuation-reviewer", "administrator"), META={})
    decide(
        reviewer,
        count.approval_id,
        approve=True,
        reason="Independent impairment evidence inspected",
    )
    assert stock.position(op.item.pk)["value"] == 950
    assert stock.reconciliation()["difference"] == 0
