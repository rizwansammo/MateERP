from datetime import date
from decimal import Decimal

import pytest

from apps.accounting.models import JournalEntry
from apps.accounting.services import setup
from apps.company.models import FinancialParty
from apps.company.services import update_business_settings
from apps.founders.services import planning, sharing
from apps.purchasing.services import payables, recurring

from .test_planning import setup_plan

pytestmark = pytest.mark.django_db


def test_foreign_estimate_stays_frozen_when_actual_occurrence_posts_at_another_rate(founder_books):
    f = founder_books
    setup_plan(f)
    update_business_settings(f.request, {"enabled_currencies": ["BDT", "USD"]})
    vendor = payables.save_vendor(f.request, {"name": "USD hosting", "currency": "USD"})
    schedule = recurring.save_schedule(
        f.request,
        {
            "name": "Foreign recurring cost",
            "vendor_id": vendor.pk,
            "currency": "USD",
            "frequency": "monthly",
            "interval": 1,
            "start_date": "2026-01-15",
            "description": "Hosting",
            "account_id": f.accounts["5100"].pk,
            "amount": "20",
            "payment_mode": "accrued",
        },
    )
    inputs = {
        "name": "Original USD estimate",
        "starts": "2026-01-01",
        "months": 2,
        "schedule_ids": [schedule.pk],
    }
    missing = planning.forecast(f.request, inputs)
    assert not missing["complete"]
    assert missing["rows"][0]["estimated_base_cost"] is None
    setup.add_rate(
        f.request,
        {
            "currency": "USD",
            "effective_date": date(2026, 1, 1),
            "value": "100",
            "source": "Explicit planning estimate",
        },
    )
    saved = planning.forecast(f.request, inputs, save=True)
    assert saved.snapshot["complete"]
    assert Decimal(saved.snapshot["rows"][0]["estimated_base_cost"]) == 2000
    assert "Explicit planning estimate" in saved.snapshot["rows"][0]["rate_source"]
    setup.add_rate(
        f.request,
        {
            "currency": "USD",
            "effective_date": date(2026, 1, 15),
            "value": "120",
            "source": "Actual occurrence rate",
        },
    )
    result = recurring.run_due(date(2026, 1, 15), runner=f.request.user, schedule_ids=[schedule.pk])
    assert result[0]["status"] == "drafted"
    expense = payables.post_expense(f.request, result[0]["expense"])
    assert expense.exchange_rate == 120
    assert expense.base_total == 2400
    journals = JournalEntry.objects.count()
    actual = planning.progress(f.request, saved)[0]["posted_costs"]
    assert len(actual) == 1
    assert Decimal(actual[0]["estimated_base_cost"]) == 2000
    assert Decimal(actual[0]["actual_base_cost"]) == 2400
    assert Decimal(actual[0]["base_cost_variance"]) == 400
    assert Decimal(actual[0]["actual_rate"]) == 120
    assert actual[0]["journal_id"] == str(expense.journal_id)
    # Pausing stops estimates, not the actual January source; selecting its ID
    # as well cannot count the same generated expense twice.
    recurring.set_status(f.request, schedule.pk, "paused")
    refreshed = planning.forecast(f.request, {**inputs, "expense_ids": [expense.pk]})
    assert len(refreshed["rows"][0]["sources"]) == 1
    assert Decimal(refreshed["rows"][0]["cost"]) == 20
    assert Decimal(refreshed["rows"][1]["cost"]) == 0
    saved.refresh_from_db()
    expense.refresh_from_db()
    assert Decimal(saved.snapshot["rows"][0]["estimated_base_cost"]) == 2000
    assert expense.exchange_rate == 120
    assert JournalEntry.objects.count() == journals


def test_custom_50_30_20_and_self_sustaining_are_independent_of_ownership_and_cash(founder_books):
    f = founder_books
    schedule, _ = setup_plan(f)
    third = FinancialParty.objects.create(
        name="Third founder", kind="individual", joined=date(2026, 1, 1), is_founder=True
    )
    policy = sharing.save_policy(
        f.request,
        {
            "name": "Independent custom allocation",
            "basis": "custom",
            "effective_from": "2026-02-01",
            "weights": {str(f.a.pk): "50", str(f.b.pk): "30", str(third.pk): "20"},
        },
    )
    sharing.activate(f.request, policy.pk)
    inputs = {"starts": "2026-02-01", "months": 1, "schedule_ids": [schedule.pk]}
    row = planning.forecast(f.request, inputs)["rows"][0]
    assert {pk: Decimal(value) for pk, value in row["founders"].items()} == {
        str(f.a.pk): Decimal("3000"),
        str(f.b.pk): Decimal("1800"),
        str(third.pk): Decimal("1200"),
    }
    self_funded = planning.forecast(f.request, {**inputs, "mode": "self_sustaining"})["rows"][0]
    assert Decimal(self_funded["cost"]) == 6000
    assert Decimal(self_funded["founder_request"]) == 0
    assert all(Decimal(value) == 0 for value in self_funded["founders"].values())
    assert not JournalEntry.objects.exists()
