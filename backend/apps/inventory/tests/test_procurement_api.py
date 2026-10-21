from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounting.models import JournalEntry
from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.purchasing.models import PurchaseOrder
from apps.purchasing.services import procurement
from conftest import upload

pytestmark = pytest.mark.django_db
BASE = "/api/v1/purchasing/"


def test_purchase_independent_approval_freezes_role_and_quorum(operations, make_user, user_with):
    op = operations
    buyer = user_with("purchaser", "procurement.manage", "finance.view")
    request = SimpleNamespace(user=buyer, META={})
    order = procurement.save_order(
        request,
        {
            "vendor_id": op.vendor.pk,
            "date": op.on,
            "currency": "BDT",
            "lines": [{"item_id": op.item.pk, "quantity": "10", "unit_price": "100"}],
        },
    )
    policy = ApprovalPolicy.objects.get(category="purchase_orders")
    policy.is_required, policy.required_approvals = True, 2
    policy.save()
    procurement.submit_order(request, order.pk)
    order.refresh_from_db()
    assert order.status == "pending" and not JournalEntry.objects.exists()
    policy.required_approvals = 1
    policy.save()
    reviewer = SimpleNamespace(user=make_user("po_reviewer", "administrator"), META={})
    decide(reviewer, order.approval_id, approve=True, reason="Quantity and contract checked")
    order.refresh_from_db()
    assert order.status == "pending"
    decide(op.request, order.approval_id, approve=True, reason="Independent second review")
    order.refresh_from_db()
    assert order.status == "approved" and not JournalEntry.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_order_api_round_trip_and_private_evidence(operations, admin_client, client_for, user_with):
    op = operations
    body = {
        "vendor_id": op.vendor.pk,
        "date": str(op.on),
        "currency": "BDT",
        "lines": [{"item_id": op.item.pk, "quantity": "1.5", "unit_price": "100.00"}],
    }
    result = admin_client.post(BASE + "orders/", body, format="json")
    assert result.status_code == 201, result.json()
    order = result.json()
    assert order["total"] == "150.000000"
    url = BASE + f"orders/{order['id']}/evidence/"
    saved = admin_client.post(
        url, {"description": "Supplier delivery evidence", "file": upload()}, format="multipart"
    )
    assert saved.status_code == 201, saved.json()
    content = f"/api/v1/files/{saved.json()['file_id']}/content/"
    response = admin_client.get(content)
    assert response.status_code == 200
    assert b"".join(response.streaming_content).startswith(b"\x89PNG")
    viewer = client_for(user_with("non_evidence_reader", "finance.view"))
    assert viewer.get(content).status_code == 404
    assert viewer.get(url).status_code == 403
    bad = admin_client.post(
        url,
        {
            "description": "Unsafe upload",
            "file": SimpleUploadedFile("x.svg", b"<svg/>", content_type="image/svg+xml"),
        },
        format="multipart",
    )
    assert bad.status_code == 400
    assert admin_client.get(url).json()["count"] == 1


def test_amendment_retains_original_and_requires_new_approval(operations):
    op = operations
    data = {
        "vendor_id": op.vendor.pk,
        "date": op.on,
        "currency": "BDT",
        "lines": [{"item_id": op.item.pk, "quantity": "10", "unit_price": "100"}],
    }
    order = procurement.save_order(op.request, data)
    procurement.submit_order(op.request, order.pk)
    procurement.transition(op.request, order.pk, "issue")
    replacement = procurement.amend_order(
        op.request, order.pk, data, "Vendor authorized new delivery terms"
    )
    assert replacement.status == "draft" and replacement.revised_from_id == order.pk
    assert PurchaseOrder.objects.get(pk=order.pk).status == "cancelled"
    assert replacement.pk != order.pk and not JournalEntry.objects.exists()
