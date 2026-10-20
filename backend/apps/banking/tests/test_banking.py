from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException, ValidationError

from apps.accounting import reports
from apps.accounting.services import posting, setup
from apps.banking import services
from apps.banking.models import LedgerMatch, StatementMatch
from apps.company.services import update_business_settings

pytestmark = pytest.mark.django_db
DAY = date(2026, 10, 10)


def banks(finance):
    r, a = finance
    cash = services.save_account(
        r, {"name": "Cash", "kind": "cash", "currency": "BDT", "gl_account_id": a["1010"].pk}
    )
    bank = services.save_account(
        r,
        {
            "name": "Bank",
            "kind": "bank",
            "currency": "BDT",
            "gl_account_id": a["1020"].pk,
            "identifier": "123456789",
        },
    )
    j = posting.save_draft(
        r,
        {
            "posting_date": DAY,
            "description": "Opening",
            "lines": [
                {"account_id": cash.gl_account_id, "debit": "1000"},
                {"account_id": a["3010"].pk, "credit": "1000"},
            ],
        },
    )
    posting.post_draft(r, j.pk, "bank-opening-test")
    return cash, bank


def test_transfer_single_journal_no_income_and_idempotency(finance):
    r, _ = finance
    cash, bank = banks(finance)
    data = {
        "posting_key": "same-transfer-key",
        "bank_account_id": cash.pk,
        "destination_id": bank.pk,
        "posting_date": DAY,
        "kind": "transfer",
        "amount": "250",
        "description": "Internal transfer",
    }
    j = services.treasury(r, data)
    assert services.treasury(r, data).pk == j.pk
    assert posting.bank_position(cash.gl_account_id)[0] == 750
    assert posting.bank_position(bank.gl_account_id)[0] == 250
    assert Decimal(reports.report("pnl", DAY, DAY)["net_profit"]) == 0
    cf = reports.report("cf", DAY, DAY)
    assert Decimal(cf["receipts"]) == 1000 and Decimal(cf["payments"]) == 0
    assert Decimal(cf["difference"]) == 0
    with pytest.raises(APIException):
        services.treasury(r, {**data, "amount": "251"})


def test_overview_chart_series_are_actual_bank_book_values(finance, admin_client, monkeypatch):
    cash, bank = banks(finance)
    monkeypatch.setattr("apps.banking.api.views.timezone.localdate", lambda: DAY)
    response = admin_client.get("/api/v1/banking/overview/")
    assert response.status_code == 200
    months = response.json()["months"]
    assert len(months) == 10
    assert Decimal(months[0]["balance"]) == 0
    assert Decimal(months[-1]["accounts"][str(cash.pk)]) == 1000
    assert Decimal(months[-1]["accounts"][str(bank.pk)]) == 0
    assert sum(Decimal(v) for v in months[-1]["accounts"].values()) == Decimal(
        months[-1]["balance"]
    )


def test_foreign_rates_snapshots_and_explicit_gain(finance):
    r, a = finance
    update_business_settings(r, {"enabled_currencies": ["BDT", "USD"]})
    usd_gl = setup.save_account(
        r, {"code": "1030", "name": "USD bank", "account_type": "asset", "currency": "USD"}
    )
    usd = services.save_account(
        r, {"name": "Dollar bank", "kind": "bank", "currency": "USD", "gl_account_id": usd_gl.pk}
    )
    cash = services.save_account(
        r, {"name": "Cash", "kind": "cash", "currency": "BDT", "gl_account_id": a["1010"].pk}
    )
    setup.add_rate(
        r, {"currency": "USD", "effective_date": DAY, "value": "120", "source": "Initial"}
    )
    j = posting.save_draft(
        r,
        {
            "posting_date": DAY,
            "description": "Foreign opening",
            "lines": [
                {"account_id": usd_gl.pk, "currency": "USD", "debit": "100"},
                {"account_id": a["3010"].pk, "credit": "12000"},
            ],
        },
    )
    posting.post_draft(r, j.pk, "fx-opening-test")
    setup.add_rate(
        r, {"currency": "USD", "effective_date": DAY, "value": "130", "source": "New spot"}
    )
    data = {
        "posting_key": "fx-transfer-test",
        "kind": "transfer",
        "bank_account_id": usd.pk,
        "destination_id": cash.pk,
        "amount": "50",
        "received_amount": "6500",
        "posting_date": DAY,
        "description": "Convert dollars",
    }
    preview = services.treasury(r, data, preview=True)
    assert Decimal(preview["fx_difference"]) == 500
    with pytest.raises(ValidationError):
        services.treasury(r, data)
    services.treasury(r, {**data, "confirm_fx": True})
    assert posting.bank_position(usd_gl.pk) == (Decimal("50"), Decimal("6000"))
    assert j.lines.get(account=usd_gl).exchange_rate == 120
    assert Decimal(reports.report("pnl", DAY, DAY)["net_profit"]) == 500


def test_missing_rate_and_zero_rounding_rejected(finance):
    r, a = finance
    update_business_settings(r, {"enabled_currencies": ["BDT", "USD"]})
    with pytest.raises(ValidationError):
        posting.save_draft(
            r,
            {
                "posting_date": DAY,
                "description": "No rate",
                "lines": [{"account_id": a["1010"].pk, "currency": "USD", "debit": "10"}],
            },
        )


def statement(finance, bank, amount="250"):
    return services.create_statement(
        finance[0],
        {
            "bank_account_id": bank.pk,
            "reference": "October statement",
            "start": date(2026, 10, 1),
            "end": date(2026, 10, 31),
            "opening_balance": "0",
            "closing_balance": amount,
            "lines": [{"date": DAY, "description": "Transfer", "amount": amount}],
        },
    )


def test_reconciliation_matches_complete_reopen_and_guard(finance):
    r, _ = finance
    cash, bank = banks(finance)
    j = services.treasury(
        r,
        {
            "posting_key": "rec-transfer-key",
            "kind": "transfer",
            "bank_account_id": cash.pk,
            "destination_id": bank.pk,
            "posting_date": DAY,
            "amount": "250",
            "description": "Transfer",
        },
    )
    rec = statement(finance, bank)
    line = j.lines.get(account_id=bank.gl_account_id)
    stmt = rec.statement.lines.first()
    with pytest.raises(APIException):
        services.complete(r, rec.pk)
    group = services.match(r, rec.pk, [stmt.pk], [line.pk])
    with pytest.raises(ValidationError):
        services.match(r, rec.pk, [stmt.pk], [line.pk])
    rec = services.complete(r, rec.pk)
    assert rec.is_complete
    with pytest.raises(APIException):
        services.unmatch(r, group.pk)
    with pytest.raises(IntegrityError), transaction.atomic():
        LedgerMatch.objects.filter(group=group).update(is_active=False)
    services.complete(r, rec.pk, reopen=True, reason="Bank correction")
    services.unmatch(r, group.pk)
    assert not StatementMatch.objects.filter(is_active=True).exists()


def test_statement_arithmetic_and_overlap(finance):
    _, bank = banks(finance)
    statement(finance, bank)
    with pytest.raises(APIException):
        statement(finance, bank)


def test_masked_bank_identifier_and_permissions(finance, admin_client, make_user, client_for):
    _, bank = banks(finance)
    rows = admin_client.get("/api/v1/banking/accounts/").json()["results"]
    assert next(row for row in rows if row["id"] == bank.pk)["identifier"] == "••••6789"
    viewer = client_for(make_user("bankviewer"))
    result = viewer.get(f"/api/v1/banking/accounts/{bank.pk}/")
    assert result.status_code == 200 and result.json()["identifier"] == "••••6789"
    assert viewer.post("/api/v1/accounting/journals/", {}, format="json").status_code == 403
    assert (
        admin_client.get(f"/api/v1/banking/accounts/{bank.pk}/").json()["identifier"] == "123456789"
    )
