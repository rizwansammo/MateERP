from datetime import date
from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.accounting.services import setup
from apps.banking.services import save_account
from apps.company.services import update_business_settings
from apps.core.exceptions import BusinessRuleViolation
from apps.founders.services import corporate, reports

pytestmark = pytest.mark.django_db


def test_reimbursement_uses_original_liability_and_weighted_bank_carrying_value(founder_books):
    f = founder_books
    update_business_settings(f.request, {"enabled_currencies": ["BDT", "USD"]})
    gl = setup.save_account(
        f.request,
        {
            "code": "FUSD",
            "name": "Founder USD bank",
            "account_type": "asset",
            "currency": "USD",
        },
    )
    bank = save_account(
        f.request,
        {
            "name": "Founder USD bank",
            "kind": "bank",
            "currency": "USD",
            "gl_account_id": gl.pk,
        },
    )
    setup.add_rate(
        f.request,
        {
            "currency": "USD",
            "effective_date": date(2026, 2, 1),
            "value": "100",
            "source": "Initial rate",
        },
    )
    setup.add_rate(
        f.request,
        {
            "currency": "USD",
            "effective_date": date(2026, 2, 2),
            "value": "120",
            "source": "Later rate",
        },
    )
    for index, on in enumerate(["2026-02-01", "2026-02-02"]):
        tx = corporate.record_transaction(
            f.request,
            {
                "kind": "receipt",
                "classification": "pending",
                "party_id": f.a.pk,
                "date": on,
                "currency": "USD",
                "amount": "100",
                "bank_id": bank.pk,
            },
            f"fx-founder-receipt-{index}",
        )
        corporate.verify(f.reviewer, tx.pk, {})
    expense = corporate.record_transaction(
        f.request,
        {
            "kind": "expense",
            "classification": "payable",
            "party_id": f.a.pk,
            "date": "2026-02-01",
            "currency": "USD",
            "expense": {
                "description": "Foreign founder expense",
                "account_id": f.accounts["5100"].pk,
                "amount": "20",
            },
        },
        "fx-founder-expense",
    )
    expense = corporate.verify(f.reviewer, expense.pk, {})
    reimbursement = corporate.record_transaction(
        f.request,
        {
            "kind": "reimbursement",
            "classification": "payable",
            "party_id": f.a.pk,
            "date": "2026-02-03",
            "currency": "USD",
            "amount": "10",
            "bank_id": bank.pk,
            "allocations": [{"obligation_id": expense.obligation.pk, "amount": "10"}],
        },
        "fx-founder-reimbursement",
    )
    quote = corporate.preview(f.request, reimbursement.pk)
    assert abs(Decimal(quote["fx_difference"])) == 100
    with pytest.raises(BusinessRuleViolation):
        corporate.verify(f.reviewer, reimbursement.pk, {})
    with pytest.raises(ValidationError):
        corporate.verify(
            f.reviewer, reimbursement.pk, {"quote_fingerprint": quote["quote_fingerprint"]}
        )
    posted = corporate.verify(
        f.reviewer,
        reimbursement.pk,
        {
            "quote_fingerprint": quote["quote_fingerprint"],
            "confirm_fx": True,
        },
    )
    assert posted.journal.lines.get(account=gl).base_credit == 1100
    assert corporate.outstanding(expense.obligation) == (Decimal("10"), Decimal("1000"))
    assert all(Decimal(row["difference"]) == 0 for row in reports.reconciliation(f.request))
