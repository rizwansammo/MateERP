from datetime import date
from types import SimpleNamespace

import pytest

from apps.billing.services import invoices, payments
from apps.billing.services.overview import fiscal_months
from apps.billing.tests.conftest import DAY, as_user, issued
from apps.billing.tests.test_payments import record, verify
from apps.purchasing.services import payables

pytestmark = pytest.mark.django_db


def test_fiscal_chart_starts_in_the_configured_year():
    start, months = fiscal_months(SimpleNamespace(fiscal_year_start_month=7), date(2026, 6, 10))
    assert start == date(2025, 7, 1)
    assert len(months) == 12 and months[-1] == "2026-06"


def test_sales_charts_keep_original_month_and_show_reversals_when_posted(
    commerce, client_for, monkeypatch
):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda: date(2026, 11, 20))
    invoice = issued(commerce)
    payment = verify(commerce, record(commerce, invoice, "11000", "chart-collection"))
    payments.reverse_payment(
        as_user(commerce.users.verifier), payment.pk, "Returned transfer", date(2026, 11, 10)
    )
    client = client_for(commerce.users.viewer)
    data = client.get("/api/v1/billing/overview/").json()
    months = {p["month"]: p for p in data["series"]}
    assert months["2026-10"]["collected"] == "11000.000000"
    assert months["2026-11"]["collected"] == "-11000.000000"
    assert data["aging"][1]["amount"] == "11000.000000"
    invoices.void_invoice(
        as_user(commerce.users.issuer), invoice.pk, "Cancelled service", date(2026, 11, 11)
    )
    data = client.get("/api/v1/billing/overview/").json()
    months = {p["month"]: p for p in data["series"]}
    assert months["2026-10"]["invoiced"] == "11000.000000"
    assert months["2026-11"]["invoiced"] == "-11000.000000"
    assert all(row["count"] == 0 for row in data["aging"])


def test_purchase_chart_uses_posted_expense_accounts_and_excludes_input_tax(commerce, client_for):
    vendor = payables.save_vendor(commerce.admin, {"name": "Chart supplier", "currency": "BDT"})
    bill = payables.save_bill(
        commerce.admin,
        {
            "vendor_id": vendor.pk,
            "vendor_reference": "CHART-BILL",
            "bill_date": DAY,
            "lines": [
                {
                    "description": "Cost",
                    "unit_price": "200",
                    "account_id": commerce.books.accounts["6100"].pk,
                    "tax_code_id": commerce.books.vat.pk,
                }
            ],
        },
    )
    payables.post_bill(commerce.admin, bill.pk)
    data = client_for(commerce.users.viewer).get("/api/v1/purchasing/overview/").json()
    october = next(p for p in data["series"] if p["month"] == "2026-10")
    assert october["expense"] == "200.000000"
    assert data["categories"][0]["amount"] == "200.000000"
    assert data["top_vendors"] == [{"label": "Chart supplier", "amount": "200.000000"}]
    assert october[data["expense_series"][0]["key"]] == "200.000000"
    assert data["spend_this_month"] == "220.000000"
