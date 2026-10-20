import pytest

from apps.billing.tests.conftest import issued
from apps.sales.services import save_project

pytestmark = pytest.mark.django_db


def test_project_margin_excludes_collected_output_tax(commerce, client_for):
    project = save_project(
        commerce.admin,
        {
            "reference": "PROJECT-TAX",
            "name": "Tax-aware project",
            "customer_id": commerce.customer.pk,
            "currency": "BDT",
            "contract_value": "20000",
        },
    )
    issued(commerce, project_id=project.pk)
    response = client_for(commerce.users.viewer).get(
        f"/api/v1/billing/projects/{project.pk}/financials/"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["invoiced"] == "11000.000000"
    assert data["net_revenue"] == data["margin"] == "10000.000000"
    assert data["uninvoiced"] == "10000.000000"


def test_project_profit_includes_foreign_costs_at_historical_ledger_value(commerce, client_for):
    from apps.accounting.services import setup
    from apps.billing.tests.conftest import DAY
    from apps.company.services import update_business_settings
    from apps.purchasing.services import payables

    project = save_project(
        commerce.admin,
        {
            "reference": "CROSS-CURRENCY",
            "name": "Foreign costs",
            "customer_id": commerce.customer.pk,
            "currency": "BDT",
            "contract_value": "20000",
        },
    )
    issued(commerce, project_id=project.pk)
    update_business_settings(commerce.admin, {"enabled_currencies": ["BDT", "USD"]})
    setup.add_rate(
        commerce.admin,
        {"currency": "USD", "effective_date": DAY, "value": "120", "source": "Historical cost"},
    )
    vendor = payables.save_vendor(commerce.admin, {"name": "Overseas supplier", "currency": "USD"})
    expense = payables.save_expense(
        commerce.admin,
        {
            "expense_date": DAY,
            "project_id": project.pk,
            "vendor_id": vendor.pk,
            "currency": "USD",
            "description": "Foreign project service",
            "amount": "2",
            "payment_mode": "accrued",
            "account_id": commerce.books.accounts["6100"].pk,
        },
    )
    payables.post_expense(commerce.admin, expense.pk)
    setup.add_rate(
        commerce.admin,
        {"currency": "USD", "effective_date": DAY, "value": "130", "source": "Later rate"},
    )
    data = (
        client_for(commerce.users.viewer)
        .get(f"/api/v1/billing/projects/{project.pk}/financials/")
        .json()
    )
    assert data["base_currency"] == "BDT"
    assert data["base_revenue"] == "10000.000000"
    assert data["base_costs"] == "240.000000"
    assert data["base_margin"] == "9760.000000"
    assert data["cost_lines"][0]["currency"] == "USD"
    assert data["cost_lines"][0]["amount"] == "2.000000"


def test_issued_non_milestone_invoice_locks_project_identity(commerce):
    from apps.core.exceptions import BusinessRuleViolation

    project = save_project(
        commerce.admin,
        {
            "reference": "LOCKED-PROJECT",
            "name": "Stable history",
            "customer_id": commerce.customer.pk,
            "currency": "BDT",
            "contract_value": "20000",
        },
    )
    issued(commerce, project_id=project.pk)
    with pytest.raises(BusinessRuleViolation):
        save_project(commerce.admin, {"contract_value": "10000"}, project.pk)
    project.refresh_from_db()
    assert project.contract_value == 20000
    assert (
        save_project(commerce.admin, {"notes": "Administrative note"}, project.pk).notes
        == "Administrative note"
    )
