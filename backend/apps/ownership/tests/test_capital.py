from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.accounting.models import JournalEntry
from apps.company.models import FinancialParty
from apps.founders.services import corporate, reports
from apps.ownership.api.serializers import exact_register_json
from apps.ownership.services import register

from .test_register import documented, formal_opening

pytestmark = pytest.mark.django_db


def test_issuance_dilution_unpaid_commitment_and_actual_capital_are_distinct(
    founder_books, make_user
):
    f = founder_books
    reviewer = SimpleNamespace(user=make_user("capital-reviewer", "administrator"), META={})
    cls = formal_opening(f, reviewer)
    investor = FinancialParty.objects.create(
        name="External investor",
        kind="organization",
        joined=date(2026, 1, 1),
        is_shareholder=True,
    )
    obj = register.propose(
        f.request,
        {
            "kind": "issuance",
            "title": "New investor subscription",
            "effective_date": "2026-03-01",
            "share_class_id": cls.pk,
            "rationale": "Documented issue",
            "legal_reference": "ISS-01",
            "lines": [{"recipient_id": investor.pk, "units": 2500, "price": "120"}],
        },
        "new-issue-2500",
    )
    assert register.holdings(date(2026, 3, 1))[str(cls.pk)]["total"] == 10000
    documented(f, obj, reviewer)
    current = register.holdings(date(2026, 3, 1))[str(cls.pk)]
    assert current["total"] == 12500
    assert Decimal(current["percentages"][str(f.a.pk)]) == 40
    assert Decimal(current["percentages"][str(investor.pk)]) == 20
    assert not JournalEntry.objects.exists()
    capital = reports.capital(f.request)["classes"][0]
    assert Decimal(capital["paid_in"]) == 0
    assert Decimal(capital["unpaid_commitments"]) == 1300000
    payment = corporate.record_transaction(
        f.request,
        {
            "kind": "receipt",
            "classification": "share_capital",
            "party_id": investor.pk,
            "date": "2026-03-01",
            "currency": "BDT",
            "amount": "300000",
            "bank_id": f.bank.pk,
            "issuance_id": obj.pk,
        },
        "capital-receipt-0001",
    )
    corporate.verify(f.reviewer, payment.pk, {})
    payment.refresh_from_db()
    values = {line.account.control: line.credit for line in payment.journal.lines.all()}
    assert values["share_capital"] == Decimal("250000")
    assert values["share_premium"] == Decimal("50000")
    assert all(Decimal(row["difference"]) == 0 for row in reports.reconciliation(f.request))
    assert Decimal(reports.capital(f.request)["classes"][0]["paid_in"]) == 300000


def test_below_par_issuance_is_rejected_before_authorization(founder_books, make_user):
    f = founder_books
    reviewer = SimpleNamespace(user=make_user("par-reviewer", "administrator"), META={})
    cls = formal_opening(f, reviewer)
    with pytest.raises(ValidationError):
        register.propose(
            f.request,
            {
                "kind": "issuance",
                "title": "Below configured par",
                "effective_date": "2026-03-01",
                "share_class_id": cls.pk,
                "rationale": "Invalid",
                "legal_reference": "INVALID",
                "lines": [{"recipient_id": f.a.pk, "units": 1, "price": "99.99"}],
            },
            "below-par-issue",
        )


def test_large_register_units_are_exact_at_browser_boundary():
    huge = 9007199254740993
    assert exact_register_json({"units": {"1": huge}, "total": huge}) == {
        "units": {"1": "9007199254740993"},
        "total": "9007199254740993",
    }
