from datetime import date
from types import SimpleNamespace

import pytest

from apps.accounting.services.setup import save_account
from apps.catalog import services as catalog
from apps.catalog.models import Unit
from apps.inventory.services import save_location
from apps.purchasing.services.payables import save_vendor


@pytest.fixture
def operations(books):
    accounts = books.accounts
    for code, name, typ, purpose in (
        ("1200", "Inventory", "asset", "inventory"),
        ("2050", "Goods received not invoiced", "liability", "grni"),
    ):
        accounts[code] = save_account(
            books.request,
            {
                "code": code,
                "name": name,
                "account_type": typ,
                "parent_id": accounts["1000" if typ == "asset" else "2000"].pk,
                "control": purpose,
            },
        )
    unit = Unit.objects.create(code="EA", name="Each")
    item = catalog.save_item(
        books.request,
        {
            "code": "WIDGET",
            "name": "Widget",
            "currency": "BDT",
            "kind": "stock",
            "unit_id": unit.pk,
            "inventory_account_id": accounts["1200"].pk,
            "cogs_account_id": accounts["5100"].pk,
        },
    )
    location = save_location(books.request, {"code": "MAIN", "name": "Main warehouse"})
    vendor = save_vendor(books.request, {"name": "Parts supplier", "currency": "BDT"})
    return SimpleNamespace(
        books=books,
        request=books.request,
        item=item,
        location=location,
        vendor=vendor,
        on=date(2026, 10, 1),
    )
