"""Purchasing HTTP contract: vendors, bills, expenses, payments, history and AP checks."""

import pytest

from apps.banking import services as banking

pytestmark = pytest.mark.django_db
BASE = "/api/v1/purchasing/"


@pytest.fixture
def setup_ap(books, admin_client):
    bank = banking.save_account(
        books.request,
        {
            "name": "Bank",
            "kind": "bank",
            "currency": "BDT",
            "gl_account_id": books.accounts["1020"].pk,
        },
    )
    vendor = admin_client.post(
        f"{BASE}vendors/", {"name": "Hosting Co", "currency": "BDT"}, format="json"
    ).json()
    return books, bank, vendor


def test_bill_payment_history_and_reconciliation(setup_ap, admin_client, client_for, user_with):
    books, bank, vendor = setup_ap
    assert vendor["code"] == "VEN-00001"
    bill = admin_client.post(
        f"{BASE}bills/",
        {
            "vendor_id": vendor["id"],
            "vendor_reference": "H-1001",
            "bill_date": "2026-10-05",
            "lines": [
                {
                    "description": "VPS",
                    "unit_price": "5000",
                    "account_id": books.accounts["6100"].pk,
                    "tax_code_id": books.vat.pk,
                }
            ],
        },
        format="json",
    )
    assert bill.status_code == 201, bill.json()
    posted = admin_client.post(f"{BASE}bills/{bill.json()['id']}/post/").json()
    assert posted["number"] == "BILL-2026-001" and posted["outstanding"] == "5500.000000"
    duplicate = admin_client.post(
        f"{BASE}bills/",
        {
            "vendor_id": vendor["id"],
            "vendor_reference": "h 1001",
            "bill_date": "2026-10-06",
            "lines": [
                {
                    "description": "VPS",
                    "unit_price": "5000",
                    "account_id": books.accounts["6100"].pk,
                }
            ],
        },
        format="json",
    )
    assert (
        duplicate.status_code == 409
        and duplicate.json()["error"]["code"] == "duplicate_vendor_invoice"
    )
    body = {
        "vendor_id": vendor["id"],
        "bank_account_id": bank.pk,
        "payment_date": "2026-10-10",
        "amount": "5500",
        "allocations": [{"bill_id": posted["id"], "amount": "5500"}],
    }
    quote = admin_client.post(f"{BASE}payments/preview/", body, format="json").json()
    paid = admin_client.post(
        f"{BASE}payments/",
        {**body, "quote_fingerprint": quote["quote_fingerprint"]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="http-vendor-pay-1",
    )
    assert paid.status_code == 201, paid.json()
    assert paid.json()["allocations"][0]["document"] == "BILL-2026-001"
    history = admin_client.get(f"{BASE}history/").json()
    assert {row["kind"] for row in history} == {"Vendor bill", "Vendor payment"}
    recon = admin_client.get(f"{BASE}reconciliation/").json()
    assert recon["difference"] == "0.000000" and recon["ledger"] == "0.000000"
    statement = admin_client.get(f"{BASE}vendors/{vendor['id']}/statement/").json()
    assert statement[-1]["balance"] == "0.000000"
    viewer = client_for(user_with("viewer", "finance.view"))
    assert (
        viewer.post(
            f"{BASE}payments/", body, format="json", HTTP_IDEMPOTENCY_KEY="viewer-pay-1"
        ).status_code
        == 403
    )


def test_expense_modes_through_http(setup_ap, admin_client):
    books, bank, vendor = setup_ap
    paid = admin_client.post(
        f"{BASE}expenses/",
        {
            "description": "Domain renewal",
            "expense_date": "2026-10-03",
            "payment_mode": "paid",
            "bank_account_id": bank.pk,
            "account_id": books.accounts["6100"].pk,
            "amount": "1200",
        },
        format="json",
    )
    assert paid.status_code == 201, paid.json()
    posted = admin_client.post(f"{BASE}expenses/{paid.json()['id']}/post/").json()
    assert posted["status"] == "paid" and posted["number"] == "EXP-2026-0001"
    accrued = admin_client.post(
        f"{BASE}expenses/",
        {"description": "Cleaning", "expense_date": "2026-10-03", "payment_mode": "accrued"},
        format="json",
    )
    assert accrued.status_code == 400
    overview = admin_client.get(f"{BASE}overview/").json()
    assert overview["spend_this_month"] == "1200.000000"
