from datetime import date
from decimal import Decimal

import pytest
from django.db import DatabaseError, transaction

from apps.accounting.models import JournalEntry
from apps.catalog import services as catalog
from apps.catalog.models import ItemProfile, Unit
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory import services as stock
from apps.inventory.models import Movement
from apps.purchasing.services import payables, procurement

pytestmark = pytest.mark.django_db


def order_and_receive(op, price, key):
    order = procurement.save_order(
        op.request,
        {
            "vendor_id": op.vendor.pk,
            "date": op.on,
            "currency": "BDT",
            "lines": [{"item_id": op.item.pk, "quantity": "10", "unit_price": price}],
        },
    )
    procurement.submit_order(op.request, order.pk)
    assert not JournalEntry.objects.exists() or Movement.objects.exists()
    procurement.transition(op.request, order.pk, "issue")
    receipt = procurement.receive(
        op.request,
        {
            "order_line_id": order.lines.get().pk,
            "date": op.on,
            "quantity": "10",
            "location_id": op.location.pk,
            "reference": "Delivery " + key,
            "reason": "Accepted counted goods",
            "key": key,
        },
    )
    return order, receipt


def test_weighted_average_receipt_count_transfer_and_gl(operations):
    op = operations
    order_and_receive(op, "100", "receipt-key-0001")
    order_and_receive(op, "200", "receipt-key-0002")
    assert stock.position(op.item.pk) == {
        "quantity": Decimal("20"),
        "value": Decimal("3000"),
        "average_cost": Decimal("150"),
    }
    reduction = {
        "item_id": op.item.pk,
        "location_id": op.location.pk,
        "date": op.on,
        "quantity": "-5",
        "expected_quantity": "20",
        "offset_account_id": op.books.accounts["5100"].pk,
        "reason": "Documented damaged-stock count",
        "key": "count-key-000001",
    }
    move = stock.adjust(op.request, reduction)
    assert move.base_value == Decimal("-750")
    assert stock.adjust(op.request, reduction).pk == move.pk
    assert stock.position(op.item.pk)["value"] == Decimal("2250")
    second = stock.save_location(op.request, {"code": "SECOND", "name": "Second warehouse"})
    count = JournalEntry.objects.count()
    stock.transfer(
        op.request,
        {
            "item_id": op.item.pk,
            "from_location_id": op.location.pk,
            "to_location_id": second.pk,
            "date": op.on,
            "quantity": "2",
            "reason": "Internal transfer",
            "key": "transfer-000001",
        },
    )
    assert JournalEntry.objects.count() == count
    assert stock.position(op.item.pk, second.pk)["quantity"] == 2
    assert stock.reconciliation()["difference"] == 0
    with pytest.raises(BusinessRuleViolation):
        stock.save_location(op.request, {"is_active": False}, second.pk)


def test_source_retries_chronology_negative_and_immutable(operations):
    op = operations
    order, receipt = order_and_receive(op, "100", "receipt-immutable")
    assert (
        procurement.receive(
            op.request,
            {
                "order_line_id": order.lines.get().pk,
                "date": op.on,
                "quantity": "10",
                "location_id": op.location.pk,
                "reference": "Delivery receipt-immutable",
                "reason": "Accepted counted goods",
                "key": "receipt-immutable",
            },
        ).pk
        == receipt.pk
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        Movement.objects.filter(pk=receipt.movement_id).update(base_value="5000")
    base = {
        "item_id": op.item.pk,
        "location_id": op.location.pk,
        "date": op.on,
        "expected_quantity": "10",
        "offset_account_id": op.books.accounts["5100"].pk,
        "reason": "Count correction",
        "key": "count-key-immutable",
    }
    with pytest.raises(BusinessRuleViolation):
        stock.adjust(op.request, {**base, "quantity": "-11"})
    with pytest.raises(BusinessRuleViolation):
        stock.adjust(op.request, {**base, "quantity": "-1", "date": date(2026, 9, 30)})
    with pytest.raises(BusinessRuleViolation):
        stock.adjust(op.request, {**base, "quantity": "-1", "expected_quantity": "9"})


def test_matched_bill_clears_grni_without_second_inventory(operations):
    op = operations
    order, receipt = order_and_receive(op, "100", "receipt-to-match")
    bill = payables.save_bill(
        op.request,
        {
            "vendor_id": op.vendor.pk,
            "vendor_reference": "SUP-1001",
            "bill_date": op.on,
            "due_date": op.on,
            "currency": "BDT",
            "lines": [
                {
                    "description": "Widgets",
                    "quantity": "10",
                    "unit_price": "100",
                    "account_id": op.books.accounts["6100"].pk,
                }
            ],
        },
    )
    procurement.match_bill(
        op.request, bill.lines.get().pk, [{"receipt_id": receipt.pk, "quantity": "10"}]
    )
    payables.post_bill(op.request, bill.pk)
    bill.refresh_from_db()
    assert bill.journal.lines.get(account__control="grni").base_debit == Decimal("1000")
    assert not bill.journal.lines.filter(account__control="inventory").exists()
    assert not bill.journal.lines.filter(account__account_type="expense").exists()
    assert stock.reconciliation()["difference"] == 0
    procurement.transition(op.request, order.pk, "close", "All received and matched")


def test_purchase_order_frozen_content_and_overdelivery(operations):
    op = operations
    order, receipt = order_and_receive(op, "100", "receipt-frozen-01")
    with pytest.raises(DatabaseError), transaction.atomic():
        type(order).objects.filter(pk=order.pk).update(total="1")
    with pytest.raises(DatabaseError), transaction.atomic():
        order.lines.update(quantity="99")
    with pytest.raises(BusinessRuleViolation):
        procurement.receive(
            op.request,
            {
                "order_line_id": receipt.order_line_id,
                "date": op.on,
                "quantity": "1",
                "location_id": op.location.pk,
                "reference": "Over-delivery",
                "reason": "No authority",
                "key": "over-receipt-0001",
            },
        )


def test_overview_reconciles_cost_and_keeps_units_separate(
    operations, admin_client, client_for, user_with
):
    op = operations
    order_and_receive(op, "100", "summary-receipt-001")
    ItemProfile.objects.filter(item=op.item).update(reorder_level="12")
    kilograms = Unit.objects.create(code="KG", name="Kilograms")
    catalog.save_item(
        op.request,
        {
            "code": "BULK",
            "name": "Bulk material",
            "currency": "BDT",
            "kind": "stock",
            "unit_id": kilograms.pk,
            "inventory_account_id": op.books.accounts["1200"].pk,
            "cogs_account_id": op.books.accounts["5100"].pk,
        },
    )
    journals = JournalEntry.objects.count()
    response = admin_client.get("/api/v1/inventory/summary/")
    assert response.status_code == 200, response.json()
    result = response.json()
    assert Decimal(result["stock_value"]) == stock.reconciliation()["gl_value"] == 1000
    assert result["tracked_items"] == 2 and result["low_stock_count"] == 2
    assert result["locations"] == 1
    assert {r["unit"]: Decimal(r["quantity"]) for r in result["unit_totals"]} == {
        "EA": Decimal("10"),
        "KG": Decimal("0"),
    }
    assert result["by_item"][0] == {"label": "Widget", "amount": "1000.000000"}
    assert any(r["id"] == op.item.pk and Decimal(r["quantity"]) == 10 for r in result["low_stock"])
    assert JournalEntry.objects.count() == journals
    assert (
        client_for(user_with("no_stock_view")).get("/api/v1/inventory/summary/").status_code == 403
    )
