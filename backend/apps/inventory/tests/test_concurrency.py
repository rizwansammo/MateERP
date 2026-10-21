"""Independent PostgreSQL connections competing for the same stock/cost pool."""

import pytest

from apps.accounting.tests.test_concurrency import race
from apps.inventory import counts
from apps.inventory import services as stock
from apps.inventory.models import Movement, StockCount
from apps.purchasing.services import procurement, reconciliation

from .test_stock import order_and_receive

pytestmark = pytest.mark.django_db(transaction=True)


def test_concurrent_counts_cannot_overissue_the_same_available_stock(operations):
    op = operations
    order_and_receive(op, "100", "concurrency-stock-receipt")
    data = {
        "item_id": op.item.pk,
        "location_id": op.location.pk,
        "date": op.on,
        "quantity": "-7",
        "expected_quantity": "10",
        "offset_account_id": op.books.accounts["5100"].pk,
        "reason": "Independently requested counted-stock write-off",
    }
    results = race(
        op.request.user.pk,
        *[
            lambda request, key=key: counts.submit(request, {**data, "key": key}).pk
            for key in ("competing-count-one", "competing-count-two")
        ],
    )
    assert sum(ok for ok, _ in results) == 1
    assert StockCount.objects.count() == 1
    assert stock.position(op.item.pk)["quantity"] == 3
    assert stock.reconciliation()["difference"] == 0


def test_concurrent_same_receipt_key_has_one_stock_movement_and_journal(operations):
    op = operations
    order = procurement.save_order(
        op.request,
        {
            "vendor_id": op.vendor.pk,
            "date": op.on,
            "currency": "BDT",
            "lines": [{"item_id": op.item.pk, "quantity": "10", "unit_price": "100"}],
        },
    )
    procurement.submit_order(op.request, order.pk)
    procurement.transition(op.request, order.pk, "issue")
    data = {
        "order_line_id": order.lines.get().pk,
        "date": op.on,
        "quantity": "10",
        "location_id": op.location.pk,
        "reference": "CONCURRENT-DELIVERY",
        "reason": "Counted one delivery",
        "key": "same-concurrent-receipt",
    }
    results = race(
        op.request.user.pk,
        *[lambda request: procurement.receive(request, data).pk for _ in range(2)],
    )
    assert all(ok for ok, _ in results) and results[0][1] == results[1][1]
    assert Movement.objects.count() == 1
    assert stock.position(op.item.pk)["value"] == 1000
    assert reconciliation.receiving()["difference"] == 0
