from datetime import date
from decimal import Decimal

import pytest

from apps.accounting import reports
from apps.accounting.services import posting, setup

from .test_engine import DAY, post

pytestmark = pytest.mark.django_db


def test_ledger_search_pagination_keeps_full_running_balance(finance):
    _, a = finance
    post(finance, "100", "100", key="first-report-key", description="Opening outside range")
    # Helper's date is the same; the posting order is deterministic by journal number.
    post(finance, "20", "20", key="second-report-key", description="Search target")
    post(finance, "30", "30", key="third-report-key", description="Last activity")
    result = reports.ledger(a["1010"].pk, DAY, DAY, search="Search", page_size=1)
    assert result["count"] == 1
    assert Decimal(result["results"][0]["balance"]) == 120
    assert Decimal(result["closing"]) == 150
    second = reports.ledger(a["1010"].pk, DAY, DAY, page=2, page_size=1)
    assert Decimal(second["results"][0]["balance"]) == 120
    summary = reports.ledger(a["1000"].pk, DAY, DAY)
    assert Decimal(summary["closing"]) == 150


def test_opening_balance_and_prior_earnings_not_double_counted(finance):
    r, a = finance
    setup.create_year(r, date(2027, 1, 1))
    j = posting.save_draft(
        r,
        {
            "posting_date": DAY,
            "description": "Prior year income",
            "lines": [
                {"account_id": a["1010"].pk, "debit": "200"},
                {"account_id": a["4100"].pk, "credit": "200"},
            ],
        },
    )
    posting.post_draft(r, j.pk, "prior-earnings-report")
    bs = reports.report("bs", date(2027, 1, 1), date(2027, 5, 1))
    assert bs["balanced"] and Decimal(bs["prior_earnings"]) == 200
    # Explicit closing journal transfers income into equity; derived earnings become zero.
    close = posting.save_draft(
        r,
        {
            "posting_date": date(2026, 12, 31),
            "description": "Year-end earnings transfer",
            "lines": [
                {"account_id": a["4100"].pk, "debit": "200"},
                {"account_id": a["3100"].pk, "credit": "200"},
            ],
        },
    )
    posting.post_draft(r, close.pk, "explicit-closing-journal")
    bs = reports.report("bs", date(2027, 1, 1), date(2027, 5, 1))
    assert bs["balanced"] and Decimal(bs["prior_earnings"]) == 0 and Decimal(bs["equity"]) == 200
    ledger = reports.ledger(a["1010"].pk, date(2027, 1, 1), date(2027, 5, 1))
    assert Decimal(ledger["opening"]) == 200 and ledger["count"] == 0


def test_contra_account_does_not_overstate_assets(finance):
    r, a = finance
    contra = setup.save_account(
        r,
        {
            "code": "1509",
            "name": "Accumulated depreciation",
            "account_type": "asset",
            "normal_side": "credit",
        },
    )
    j = posting.save_draft(
        r,
        {
            "posting_date": DAY,
            "description": "Contra balance",
            "lines": [
                {"account_id": a["6100"].pk, "debit": "20"},
                {"account_id": contra.pk, "credit": "20"},
            ],
        },
    )
    posting.post_draft(r, j.pk, "contra-report-test")
    bs = reports.report("bs", DAY, DAY)
    assert bs["balanced"] and Decimal(bs["assets"]) == -20 and Decimal(bs["equity"]) == -20
