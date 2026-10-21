from datetime import date
from decimal import Decimal

import pytest
from django.db import DatabaseError, transaction
from django.db.models import Sum

from apps.accounting.models import JournalLine
from apps.accounting.services.setup import save_account
from apps.billing.services import credits, invoices, recognition
from apps.catalog import services as catalog
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory import services as stock
from apps.sales import services as sales

from .test_stock import order_and_receive

pytestmark = pytest.mark.django_db


def balance(control):
    rows = JournalLine.objects.filter(account__control=control, journal__status="posted")
    sums = rows.aggregate(d=Sum("base_debit"), c=Sum("base_credit"))
    return (sums["d"] or Decimal(0)) - (sums["c"] or Decimal(0))


def contract(op, commerce, **extra):
    for code, purpose, kind in (
        ("1250", "unbilled_revenue", "asset"),
        ("2250", "deferred_revenue", "liability"),
    ):
        save_account(
            op.request, {"code": code, "name": purpose, "account_type": kind, "control": purpose}
        )
    catalog.save_item(
        op.request, {"revision": 1, "revenue_account_id": op.books.accounts["4100"].pk}, op.item.pk
    )
    order_and_receive(op, "100", "fulfillment-stock-01")
    order = sales.save_order(
        op.request,
        {
            "customer_id": commerce.customer.pk,
            "order_date": op.on,
            **extra,
            "currency": "BDT",
            "lines": [
                {
                    "item_id": op.item.pk,
                    "description": "Contract widgets",
                    "quantity": "10",
                    "unit_price": "200",
                }
            ],
        },
    )
    sales.confirm_order(op.request, order.pk)
    line = order.lines.get()
    policy = recognition.configure(
        op.request,
        {
            "order_line_id": line.pk,
            "trigger": "control_transfer",
            "contract_reference": "SIGNED-CONTROL-TERMS-1",
            "reason": "Customer obtains control upon documented acceptance, "
            "independent of dispatch or invoice.",
        },
    )
    return order, line, policy


def invoice(op, commerce, order, line, on, qty="10"):
    return invoices.save_invoice(
        op.request,
        {
            "customer_id": commerce.customer.pk,
            "sales_order_id": order.pk,
            "issue_date": on,
            "due_date": on,
            "currency": "BDT",
            "lines": [
                {
                    "item_id": op.item.pk,
                    "sales_order_line_id": line.pk,
                    "description": "Contract widgets",
                    "quantity": qty,
                    "unit_price": "200",
                }
            ],
        },
    )


def control(op, policy, on, qty, key, **extra):
    return recognition.transfer_control(
        op.request,
        {
            "policy_id": policy.pk,
            "location_id": op.location.pk,
            "date": on,
            "quantity": qty,
            "reference": key,
            "evidence": "Documented customer acceptance and transfer of control",
            "key": key,
            **extra,
        },
    )


def test_dispatch_does_not_recognize_revenue_or_cogs(operations, commerce):
    op = operations
    _, _, policy = contract(op, commerce)
    transit = stock.save_location(op.request, {"code": "TRANSIT", "name": "Company-owned transit"})
    sent = recognition.dispatch(
        op.request,
        {
            "policy_id": policy.pk,
            "date": date(2026, 10, 15),
            "quantity": "10",
            "from_location_id": op.location.pk,
            "transit_location_id": transit.pk,
            "reference": "DISPATCH-01",
            "evidence": "Dispatch only; control remains with company",
            "key": "dispatch-in-transit-01",
        },
    )
    assert stock.position(op.item.pk)["value"] == 1000
    assert not JournalLine.objects.filter(account__account_type="revenue").exists()
    assert not JournalLine.objects.filter(account=op.books.accounts["5100"]).exists()
    assert stock.position(op.item.pk, transit.pk)["quantity"] == 10
    control(
        op,
        policy,
        date(2026, 10, 31),
        "5",
        "control-transfer-01",
        dispatch_id=str(sent.pk),
        location_id=transit.pk,
    )
    assert balance("unbilled_revenue") == 1000
    assert stock.position(op.item.pk)["value"] == 500
    recalled = recognition.recall_dispatch(
        op.request,
        sent.pk,
        {
            "date": date(2026, 11, 1),
            "quantity": "5",
            "location_id": op.location.pk,
            "reason": "Customer did not accept remaining goods",
            "key": "recall-dispatch-01",
        },
    )
    assert stock.position(op.item.pk, op.location.pk)["quantity"] == 5
    assert stock.position(op.item.pk)["value"] == 500
    with pytest.raises(DatabaseError), transaction.atomic():
        type(recalled).objects.filter(pk=recalled.pk).update(quantity="1")
    with pytest.raises(BusinessRuleViolation):
        recognition.recall_dispatch(
            op.request,
            sent.pk,
            {
                "date": date(2026, 11, 1),
                "quantity": "1",
                "location_id": op.location.pk,
                "reason": "Cannot recall customer-owned goods",
                "key": "over-recall-dispatch-01",
            },
        )


def test_project_profit_follows_control_before_invoicing_and_freezes_identity(
    operations, commerce, client_for
):
    op = operations
    project = sales.save_project(
        op.request,
        {
            "reference": "CONTROL-PROJECT",
            "name": "Control-based project",
            "customer_id": commerce.customer.pk,
            "currency": "BDT",
            "contract_value": "2000",
        },
    )
    _, _, policy = contract(op, commerce, project_id=project.pk)
    control(op, policy, date(2026, 10, 10), "2", "project-control-01")
    result = client_for(op.request.user).get(f"/api/v1/billing/projects/{project.pk}/financials/")
    assert result.status_code == 200, result.data
    assert Decimal(result.data["base_revenue"]) == 400
    assert Decimal(result.data["base_costs"]) == 200
    assert Decimal(result.data["base_margin"]) == 200
    assert Decimal(result.data["invoiced"]) == 0
    with pytest.raises(BusinessRuleViolation):
        sales.save_project(op.request, {"contract_value": "5000"}, project.pk)


def test_fulfillment_api_enforces_permissions_and_paginates(
    operations, commerce, client_for, make_user
):
    op = operations
    order, _, policy = contract(op, commerce)
    client = client_for(op.request.user)
    result = client.get(f"/api/v1/billing/fulfillment/policies/?order_id={order.pk}")
    assert result.status_code == 200 and result.data["results"][0]["id"] == policy.pk
    viewer = client_for(make_user("fulfillment-viewer"))
    result = viewer.post(
        "/api/v1/billing/fulfillment/control-transfers/", {"policy_id": policy.pk}, format="json"
    )
    assert result.status_code == 403
    assert viewer.get("/api/v1/billing/fulfillment/returns/").status_code == 200


def test_control_before_invoice_then_partial_later_control_has_one_revenue_and_cogs(
    operations, commerce
):
    op = operations
    order, line, policy = contract(op, commerce)
    first = control(op, policy, date(2026, 10, 31), "5", "control-first-01")
    assert first.base_cogs == 500 and first.base_revenue == 1000
    doc = invoice(op, commerce, order, line, date(2026, 11, 2))
    invoices.issue_invoice(op.request, doc.pk)
    doc.refresh_from_db()
    assert balance("unbilled_revenue") == 0 and balance("deferred_revenue") == -1000
    assert not doc.journal.lines.filter(account__account_type="revenue").exists()
    second = control(op, policy, date(2026, 11, 5), "5", "control-second-01")
    assert second.base_revenue == 1000
    assert balance("unbilled_revenue") == balance("deferred_revenue") == 0
    revenue = JournalLine.objects.filter(account=op.books.accounts["4100"]).aggregate(
        v=Sum("base_credit")
    )["v"]
    assert revenue == 2000
    assert stock.position(op.item.pk)["quantity"] == 0
    assert stock.reconciliation()["difference"] == 0
    assert control(op, policy, date(2026, 11, 5), "5", "control-second-01").pk == second.pk
    assert invoices.issue_invoice(op.request, doc.pk).pk == doc.pk
    with pytest.raises(BusinessRuleViolation):
        invoices.void_invoice(
            op.request, doc.pk, "Cannot silently void delivered consideration", date(2026, 11, 6)
        )


def test_invoice_before_control_and_credit_reduce_unperformed_consideration(operations, commerce):
    op = operations
    order, line, policy = contract(op, commerce)
    doc = invoice(op, commerce, order, line, date(2026, 10, 10))
    invoices.issue_invoice(op.request, doc.pk)
    assert balance("deferred_revenue") == -2000
    assert stock.position(op.item.pk)["quantity"] == 10
    assert not JournalLine.objects.filter(account=op.books.accounts["4100"]).exists()
    note = credits.request_credit_note(
        op.request,
        doc.pk,
        {
            "issue_date": date(2026, 10, 11),
            "reason": "Approved pre-delivery price concession",
            "lines": [{"invoice_line_id": doc.lines.get().pk, "amount": "100"}],
        },
        "pre-delivery-credit-01",
    )
    assert note.status == "issued"
    assert balance("deferred_revenue") == -1900
    event = control(op, policy, date(2026, 11, 1), "10", "control-after-credit-01")
    assert event.net_native == 1900 and event.base_cogs == 1000
    assert balance("deferred_revenue") == 0
    assert JournalLine.objects.filter(account=op.books.accounts["4100"]).get().base_credit == 1900


def test_credit_does_not_restock_and_accepted_return_uses_original_cost(operations, commerce):
    op = operations
    order, line, policy = contract(op, commerce)
    original = control(op, policy, date(2026, 10, 10), "10", "control-for-return-01")
    doc = invoice(op, commerce, order, line, date(2026, 10, 11))
    invoices.issue_invoice(op.request, doc.pk)
    credits.request_credit_note(
        op.request,
        doc.pk,
        {
            "issue_date": date(2026, 10, 12),
            "reason": "Two widgets accepted for credit",
            "lines": [{"invoice_line_id": doc.lines.get().pk, "amount": "400"}],
        },
        "returned-credit-01",
    )
    assert stock.position(op.item.pk)["quantity"] == 0
    # A later mapping change must not redirect the original fulfillment's return cost.
    catalog.save_item(
        op.request, {"revision": 2, "cogs_account_id": op.books.accounts["6200"].pk}, op.item.pk
    )
    returned = recognition.accept_return(
        op.request,
        {
            "transfer_id": str(original.pk),
            "date": date(2026, 10, 13),
            "quantity": "2",
            "location_id": op.location.pk,
            "reference": "RETURN-01",
            "reason": "Received and inspected original widgets",
            "key": "return-widgets-01",
        },
    )
    assert returned.base_cost == 200
    assert returned.movement.journal.lines.get(account=original.cogs_account).base_credit == 200
    assert stock.position(op.item.pk)["quantity"] == 2
    assert stock.reconciliation()["difference"] == 0
    with pytest.raises(BusinessRuleViolation):
        recognition.accept_return(
            op.request,
            {
                "transfer_id": str(original.pk),
                "date": date(2026, 10, 14),
                "quantity": "9",
                "location_id": op.location.pk,
                "reference": "RETURN-OVER",
                "reason": "Cannot return more than fulfilled",
                "key": "return-over-01",
            },
        )
