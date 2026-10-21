from types import SimpleNamespace

import pytest
from django.db import DatabaseError, transaction
from rest_framework.exceptions import PermissionDenied

from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory import services as stock
from apps.purchasing.models import SupplierReturn
from apps.purchasing.services import payables, procurement, reconciliation, returns

from .test_stock import order_and_receive

pytestmark = pytest.mark.django_db


def payload(op, **extra):
    return {
        "date": op.on,
        "quantity": "5",
        "location_id": op.location.pk,
        "variance_account_id": op.books.accounts["5100"].pk,
        "reference": "SUPPLIER-CANCEL-01",
        "reason": "Supplier accepted unmatched goods and cancelled original consideration",
        "key": "supplier-return-0001",
        **extra,
    }


def test_return_preserves_original_grni_and_discloses_weighted_average_variance(
    operations, admin_client
):
    op = operations
    _, first = order_and_receive(op, "100", "supplier-return-first")
    order_and_receive(op, "200", "supplier-return-second")
    url = f"/api/v1/purchasing/receipts/{first.pk}/supplier-returns/"
    response = admin_client.post(url, payload(op), format="json")
    assert response.status_code == 201, response.data
    returned = SupplierReturn.objects.get(pk=response.data["return_id"])
    assert (
        returned.base_value == 500 and returned.inventory_value == 750 and returned.variance == 250
    )
    assert returned.movement.original_id == first.movement_id
    assert stock.position(op.item.pk)["value"] == 2250
    assert reconciliation.receiving()["difference"] == stock.reconciliation()["difference"] == 0
    assert returns.request_return(op.request, first.pk, payload(op))["return_id"] == returned.pk
    assert admin_client.get(url).data["count"] == 1
    with pytest.raises(BusinessRuleViolation):
        returns.request_return(op.request, first.pk, payload(op, quantity="4"))
    with pytest.raises(DatabaseError), transaction.atomic():
        SupplierReturn.objects.filter(pk=returned.pk).update(variance="0")
    # Match only the remaining five units and original remaining consideration.
    bill = payables.save_bill(
        op.request,
        {
            "vendor_id": op.vendor.pk,
            "vendor_reference": "AFTER-RETURN",
            "bill_date": op.on,
            "due_date": op.on,
            "currency": "BDT",
            "lines": [
                {
                    "description": "Retained widgets",
                    "quantity": "5",
                    "unit_price": "100",
                    "account_id": op.books.accounts["5100"].pk,
                }
            ],
        },
    )
    procurement.match_bill(
        op.request, bill.lines.get().pk, [{"receipt_id": first.pk, "quantity": "5"}]
    )
    payables.post_bill(op.request, bill.pk)
    assert reconciliation.receiving()["unmatched_base"] == 2000
    assert reconciliation.receiving()["difference"] == reconciliation.payables()["difference"] == 0
    with pytest.raises(BusinessRuleViolation):
        returns.request_return(
            op.request, first.pk, payload(op, key="matched-source-return-01", quantity="1")
        )


def test_return_independent_approval_rechecks_frozen_cost_basis(operations, make_user):
    op = operations
    _, receipt = order_and_receive(op, "100", "supplier-return-reviewed")
    ApprovalPolicy.objects.filter(category="financial_adjustments").update(
        is_required=True, is_active=True
    )
    result = returns.request_return(op.request, receipt.pk, payload(op))
    assert result["status"] == "pending" and not SupplierReturn.objects.exists()
    with pytest.raises(PermissionDenied):
        decide(op.request, result["approval_id"], approve=True)
    reviewer = SimpleNamespace(user=make_user("return-reviewer", "administrator"), META={})
    decide(
        reviewer,
        result["approval_id"],
        approve=True,
        reason="Supplier cancellation and original receipt reviewed",
    )
    assert SupplierReturn.objects.count() == 1
    assert stock.position(op.item.pk)["quantity"] == 5
    assert reconciliation.receiving()["difference"] == 0
    # A second request freezes current quantity/cost and rejects an intervening event.
    pending = returns.request_return(
        op.request, receipt.pk, payload(op, key="return-stale-review", quantity="1")
    )
    other = stock.save_location(op.request, {"code": "RET-OTHER", "name": "Other"})
    stock.transfer(
        op.request,
        {
            "item_id": op.item.pk,
            "date": op.on,
            "from_location_id": op.location.pk,
            "to_location_id": other.pk,
            "quantity": "1",
            "reason": "Intervening movement",
            "key": "return-stale-transfer",
        },
    )
    with pytest.raises(BusinessRuleViolation):
        decide(reviewer, pending["approval_id"], approve=True, reason="Must recheck after transfer")
    assert SupplierReturn.objects.count() == 1
