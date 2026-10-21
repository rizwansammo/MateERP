from datetime import date

import pytest

from apps.accounting.services.setup import save_account
from apps.purchasing.services import payables


@pytest.fixture
def equipment(books):
    for code, purpose in [("1500", "fixed_assets"), ("1590", "accumulated_depreciation")]:
        save_account(
            books.request,
            {
                "code": code,
                "name": purpose,
                "account_type": "asset",
                "control": purpose,
                "normal_side": "credit" if purpose == "accumulated_depreciation" else "debit",
            },
        )
    vendor = payables.save_vendor(books.request, {"name": "Equipment vendor", "currency": "BDT"})
    bill = payables.save_bill(
        books.request,
        {
            "vendor_id": vendor.pk,
            "vendor_reference": "EQUIPMENT-001",
            "bill_date": date(2026, 1, 1),
            "due_date": date(2026, 1, 1),
            "currency": "BDT",
            "lines": [
                {
                    "description": "Server acquisition",
                    "quantity": "1",
                    "unit_price": "60000",
                    "account_id": books.accounts["6100"].pk,
                }
            ],
        },
    )
    payables.post_bill(books.request, bill.pk)
    bill.refresh_from_db()
    return bill.journal.lines.get(account=books.accounts["6100"])
