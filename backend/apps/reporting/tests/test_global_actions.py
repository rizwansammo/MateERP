"""Permission-aware search and cash-on-hand dashboard invariants."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting.services import posting
from apps.banking.models import BankAccount
from apps.sales.models import Customer

pytestmark = pytest.mark.django_db


def test_global_search_limits_input_and_enforces_financial_permissions(
    books, admin_client, make_user, client_for
):
    customer = Customer.objects.create(
        code="SEARCH-ALPHA",
        name="Enterprise Searchable Client",
        currency="BDT",
        created_by=books.request.user,
    )
    response = admin_client.get("/api/v1/reporting/search/?q=Searchable")
    assert response.status_code == 200
    assert any(
        item["category"] == "Customers"
        and item["title"] == customer.name
        and item["href"] == f"/sales/customers/{customer.pk}"
        for item in response.data
    )
    viewer = client_for(make_user("global-search-no-finance", None))
    restricted = viewer.get("/api/v1/reporting/search/?q=Searchable")
    assert restricted.status_code == 200
    assert restricted.data == []
    assert admin_client.get("/api/v1/reporting/search/?q=" + "x" * 101).status_code == 400
    assert admin_client.get("/api/v1/reporting/search/?q=a").data == []


def test_dashboard_cash_on_hand_is_distinct_from_bank_position(books, admin_client):
    BankAccount.objects.create(
        name="Petty cash",
        kind="cash",
        currency="BDT",
        gl_account=books.accounts["1010"],
    )
    BankAccount.objects.create(
        name="Main bank",
        kind="bank",
        currency="BDT",
        gl_account=books.accounts["1020"],
    )
    draft = posting.save_draft(
        books.request,
        {
            "kind": "opening",
            "posting_date": date(2026, 1, 1),
            "description": "Opening cash and bank",
            "lines": [
                {"account_id": books.accounts["1010"].pk, "debit": "175"},
                {"account_id": books.accounts["1020"].pk, "debit": "925"},
                {"account_id": books.accounts["3010"].pk, "credit": "1100"},
            ],
        },
    )
    posting.post_draft(books.request, draft.pk, "dashboard-cash-on-hand")
    response = admin_client.get(
        "/api/v1/reporting/dashboard/?range=custom&from=2026-01-01&to=2026-10-31"
    )
    assert response.status_code == 200, response.data
    metrics = response.data["metrics"]
    assert metrics[0]["key"] == "cash_on_hand"
    assert Decimal(metrics[0]["value"]) == Decimal("175")
    aggregate = next(m for m in metrics if m["key"] == "cash")
    assert Decimal(aggregate["value"]) == Decimal("1100")
    assert len(metrics) >= 14
