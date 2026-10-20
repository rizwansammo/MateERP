from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.accounting.models import (
    Account,
    AccountingPeriod,
    ExchangeRate,
    FiscalYear,
    PostingIdentity,
)
from apps.accounting.money import convert
from apps.accounting.services import posting, setup
from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.company.services import update_business_settings

from .test_engine import DAY, draft, post

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/accounting/periods/?year=invalid",
        "/api/v1/accounting/reports/tb/?period=invalid",
        "/api/v1/banking/transactions/?bank=invalid",
        "/api/v1/banking/reconciliations/?bank=invalid",
    ],
)
def test_invalid_numeric_filters_are_validation_errors(finance, admin_client, url):
    assert admin_client.get(url).status_code == 400


def test_unsafe_exact_inputs_are_standard_errors(finance, admin_client):
    _, a = finance
    for value in (1.1, "NaN", "Infinity", "-1", "0.001", "1000000000000000000"):
        response = admin_client.post(
            "/api/v1/accounting/journals/",
            {
                "posting_date": str(DAY),
                "description": "Invalid input",
                "lines": [{"account_id": a["1010"].pk, "debit": value}],
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["error"]["request_id"]


def test_conversion_rounding_and_overflow():
    assert convert(Decimal("0.01"), Decimal("1.5"), "BDT") == Decimal("0.02")
    with pytest.raises(ValidationError):
        convert(Decimal("999999999999999999"), Decimal("100"), "BDT")


def test_period_guards_and_whole_year_reopen(finance):
    r, _ = finance
    year = FiscalYear.objects.get(start=date(2026, 1, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        FiscalYear.objects.filter(pk=year.pk).update(is_closed=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        AccountingPeriod.objects.create(fiscal_year=year, start=DAY, end=date(2026, 10, 20))
    setup.set_period(r, year.pk, True, fiscal=True)
    assert not year.periods.filter(is_closed=False).exists()
    with pytest.raises(ValidationError):
        posting.post_draft(r, draft(finance).pk, "closed-year-guard")
    setup.set_period(r, year.pk, False, "Reopen for adjustment", fiscal=True)
    assert year.periods.filter(is_closed=False).count() == 12


def test_summary_history_and_posting_identity_are_guarded(finance):
    _, a = finance
    post(finance)
    for op in (
        lambda: Account.objects.filter(pk=a["1000"].pk).update(normal_side="credit"),
        lambda: Account.objects.filter(pk=a["1000"].pk).update(account_type="expense"),
        lambda: PostingIdentity.objects.all().update(fingerprint="0" * 64),
        lambda: PostingIdentity.objects.all().delete(),
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            op()


def test_rate_and_tax_revisions_are_preserved(finance, admin_client):
    r, a = finance
    update_business_settings(r, {"enabled_currencies": ["BDT", "USD"]})
    fx = setup.add_rate(
        r, {"currency": "USD", "effective_date": DAY, "value": "120", "source": "Manual"}
    )
    converted = admin_client.post(
        "/api/v1/accounting/exchange-rates/preview/",
        {"currency": "USD", "on": str(DAY), "amount": "1.25"},
        format="json",
    )
    assert converted.status_code == 200 and Decimal(converted.json()["base_amount"]) == 150
    tax = setup.save_tax(
        r,
        {
            "code": "VAT",
            "name": "Example tax",
            "revision": {
                "effective_date": DAY,
                "percent": "15",
                "input_account_id": a["1150"].pk,
                "output_account_id": a["2100"].pk,
            },
        },
    )
    revision = tax.revisions.first()
    for operation in (
        lambda: ExchangeRate.objects.filter(pk=fx.pk).update(value=121),
        lambda: tax.revisions.update(percent=16),
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            operation()
    j = posting.save_draft(
        r,
        {
            "posting_date": DAY,
            "description": "Manual tax adjustment",
            "lines": [
                {"account_id": a["1150"].pk, "debit": "15", "tax_revision_id": revision.pk},
                {"account_id": a["2010"].pk, "credit": "15"},
            ],
        },
    )
    posting.post_draft(r, j.pk, "manual-tax-guard")
    position = admin_client.get("/api/v1/accounting/tax-position/").json()
    assert Decimal(position["input"]) == 15 and Decimal(position["net"]) == -15


def test_new_sensitive_permissions_not_granted_to_finance_manager(finance, make_user, client_for):
    r, _ = finance
    manager = make_user("finance_manager_guard", "finance_manager")
    client = client_for(manager)
    assert client.get("/api/v1/accounting/journals/").status_code == 200
    period = AccountingPeriod.objects.get(start=date(2026, 10, 1))
    assert (
        client.post(f"/api/v1/accounting/periods/{period.pk}/close/", {}, format="json").status_code
        == 403
    )
    policy = ApprovalPolicy.objects.get(category="financial_adjustments")
    policy.is_required = True
    policy.approver_role = manager.role
    policy.save()
    j = post(finance)
    assert (
        client.post(
            f"/api/v1/approvals/requests/{j.approval_id}/approve/", {}, format="json"
        ).status_code
        == 403
    )


def test_rejected_manual_snapshot_can_be_revalidated_and_resubmitted(finance, make_user):
    r, _ = finance
    policy = ApprovalPolicy.objects.get(category="financial_adjustments")
    policy.is_required = True
    policy.save()
    j = post(finance)
    other = SimpleNamespace(user=make_user("rejector", "administrator"), META={})
    decide(other, j.approval_id, approve=False, reason="Needs revision")
    payload = posting.snapshot(j)
    old_approval = j.approval_id
    revised = posting.save_draft(r, payload, j.pk)
    revised = posting.post_draft(r, revised.pk, "resubmitted-after-rejection")[0]
    assert revised.revision == 2 and revised.approval_id != old_approval


def test_filtered_csv_and_export_permission(finance, admin_client, make_user, client_for):
    _, a = finance
    post(finance, description="=Untrusted text")
    post(finance, key="second-export-post", description="Selected row")
    response = admin_client.get(
        f"/api/v1/accounting/ledger/{a['1010'].pk}/?from={DAY}&to={DAY}&search=Selected&export=csv"
    )
    assert response.status_code == 200 and "Selected row" in response.content.decode()
    assert "=Untrusted" not in response.content.decode()
    all_rows = admin_client.get(
        f"/api/v1/accounting/ledger/{a['1010'].pk}/?from={DAY}&to={DAY}&export=csv"
    )
    assert "'=Untrusted" in all_rows.content.decode()
    viewer = client_for(make_user("csv_viewer"))
    assert viewer.get("/api/v1/accounting/reports/tb/?export=csv").status_code == 403
