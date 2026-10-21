from datetime import date

import pytest

from apps.accounting.models import JournalEntry
from apps.catalog import services
from apps.catalog.models import PriceRevision, Unit
from apps.core.exceptions import BusinessRuleViolation
from apps.sales.models import BillingItem

pytestmark = pytest.mark.django_db
BASE = "/api/v1/catalog/"


def test_catalog_reuses_billing_identity_and_checks_revision(books, admin_client):
    unit = admin_client.post(BASE + "units/", {"code": "hr", "name": "Hour"}, format="json").json()
    response = admin_client.post(
        BASE + "items/",
        {
            "code": "SUPPORT",
            "name": "Support",
            "kind": "service",
            "unit_id": unit["id"],
            "currency": "BDT",
            "unit_price": "100.00",
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    item = response.json()
    legacy = admin_client.get("/api/v1/sales/items/?search=SUPPORT").json()["results"][0]
    assert legacy["id"] == item["id"]
    changed = admin_client.patch(
        BASE + f"items/{item['id']}/",
        {
            "name": "Professional support",
            "revision": 1,
        },
        format="json",
    )
    assert changed.status_code == 200
    assert changed.json()["profile"]["revision"] == 2
    assert (
        admin_client.patch(
            BASE + f"items/{item['id']}/",
            {
                "name": "Stale",
                "revision": 1,
            },
            format="json",
        ).status_code
        == 409
    )
    assert not JournalEntry.objects.exists()


def test_dated_prices_and_exact_preview(books, admin_client):
    unit = Unit.objects.create(code="EA", name="Each", allows_fraction=False)
    item = services.save_item(
        books.request,
        {
            "code": "P1",
            "name": "Product",
            "currency": "BDT",
            "unit_id": unit.pk,
        },
    )
    for on, price in ((date(2026, 1, 1), "100.00"), (date(2026, 10, 1), "125.00")):
        services.add_price(
            books.request,
            item.pk,
            {
                "purpose": "sale",
                "currency": "BDT",
                "effective_date": on,
                "value": price,
                "reason": "Reviewed list price",
            },
        )
    url = BASE + f"items/{item.pk}/quote/"
    first = admin_client.post(
        url, {"date": "2026-09-30", "currency": "BDT", "quantity": "3"}, format="json"
    )
    assert first.json()["subtotal"] == "300.00"
    second = admin_client.post(
        url, {"date": "2026-10-01", "currency": "BDT", "quantity": "3"}, format="json"
    )
    assert second.json()["subtotal"] == "375.00"
    assert (
        admin_client.post(
            url,
            {
                "date": "2026-10-01",
                "currency": "BDT",
                "quantity": "0.5",
            },
            format="json",
        ).status_code
        == 400
    )
    assert PriceRevision.objects.count() == 2
    assert not JournalEntry.objects.exists()


def test_existing_unclassified_items_remain_usable(books, admin_client):
    item = BillingItem.objects.create(code="OLD", name="Legacy", currency="BDT", unit_price="1.01")
    result = admin_client.get(BASE + f"items/{item.pk}/")
    assert result.status_code == 200 and result.json()["profile"] is None
    result = admin_client.post(
        BASE + f"items/{item.pk}/quote/",
        {
            "date": "2026-01-01",
            "currency": "BDT",
            "quantity": "3",
        },
        format="json",
    )
    assert result.json()["subtotal"] == "3.03"


def test_catalog_permissions_and_unit_semantics(books, user_with, client_for):
    client = client_for(user_with("reader", "finance.view"))
    assert (
        client.post(BASE + "units/", {"code": "EA", "name": "Each"}, format="json").status_code
        == 403
    )
    unit = Unit.objects.create(code="EA", name="Each")
    services.save_item(
        books.request,
        {
            "code": "P1",
            "name": "Product",
            "currency": "BDT",
            "unit_id": unit.pk,
        },
    )
    with pytest.raises(BusinessRuleViolation):
        services.save_reference(books.request, Unit, {"allows_fraction": False}, unit.pk)
