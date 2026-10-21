from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.accounting.models import JournalEntry
from apps.company.models import FinancialParty
from apps.core.exceptions import BusinessRuleViolation
from apps.founders.models import CorporateTransaction, FundingConsumption
from apps.founders.services import planning, sharing
from apps.purchasing.services import payables, recurring

from .test_corporate import receipt

pytestmark = pytest.mark.django_db


def test_monthly_and_annual_targets_no_duplicate_occurrences(founder_books):
    f = founder_books
    policy = sharing.save_policy(
        f.request,
        {
            "name": "Equal",
            "basis": "equal",
            "effective_from": "2026-01-01",
            "weights": {str(f.a.pk): "1", str(f.b.pk): "1"},
        },
    )
    sharing.activate(f.request, policy.pk)
    vendor = payables.save_vendor(f.request, {"name": "Cloud provider", "currency": "BDT"})
    for name, amount, frequency, start in [
        ("VPS", "4000", "monthly", "2026-01-01"),
        ("Subscription", "2000", "monthly", "2026-01-01"),
        ("Domain", "1200", "yearly", "2026-12-01"),
    ]:
        recurring.save_schedule(
            f.request,
            {
                "name": name,
                "vendor_id": vendor.pk,
                "currency": "BDT",
                "frequency": frequency,
                "interval": 1,
                "start_date": start,
                "description": name,
                "account_id": f.accounts["5100"].pk,
                "amount": amount,
                "payment_mode": "accrued",
            },
        )
    result = planning.forecast(f.request, {"starts": "2026-01-01", "months": 12})
    assert len(result["rows"]) == 12
    assert result["rows"][0]["cost"] == "6000.00"
    assert result["rows"][0]["founders"][str(f.a.pk)] == "3000.00"
    assert result["rows"][-1]["cost"] == "7200.00"
    assert result["rows"][-1]["founders"][str(f.b.pk)] == "3600.00"
    assert len(result["rows"][-1]["sources"]) == 3


def setup_plan(f, *, annual=False, mode="founders"):
    policy = sharing.save_policy(
        f.request,
        {
            "name": "Equal",
            "basis": "equal",
            "effective_from": "2026-01-01",
            "weights": {str(f.a.pk): "1", str(f.b.pk): "1"},
        },
    )
    sharing.activate(f.request, policy.pk)
    vendor = payables.save_vendor(f.request, {"name": "Domain provider", "currency": "BDT"})
    schedule = recurring.save_schedule(
        f.request,
        {
            "name": "Domain" if annual else "Hosting",
            "vendor_id": vendor.pk,
            "currency": "BDT",
            "frequency": "yearly" if annual else "monthly",
            "interval": 1,
            "start_date": "2026-12-01" if annual else "2026-01-01",
            "description": "Services",
            "account_id": f.accounts["5100"].pk,
            "amount": "1200" if annual else "6000",
            "payment_mode": "accrued",
        },
    )
    plan = planning.forecast(
        f.request,
        {
            "name": "Saved forecast",
            "starts": "2026-01-01",
            "months": 12,
            "mode": mode,
        },
        save=True,
    )
    return schedule, plan


def test_partial_company_cash_and_promises_do_not_fake_receipts(founder_books):
    f = founder_books
    _, plan = setup_plan(f, mode="partial")
    receipt(f, "10000")
    journals = JournalEntry.objects.count()
    planning.pledge(
        f.request,
        {
            "plan_id": plan.pk,
            "party_id": f.a.pk,
            "month": "2026-02-01",
            "currency": "BDT",
            "amount": "999999",
            "status": "promised",
        },
    )
    coverage = planning.cover_from_company(
        f.request,
        {
            "plan_id": plan.pk,
            "bank_id": f.bank.pk,
            "month": "2026-02-01",
            "amount": "2000",
            "reference": "Approved company coverage",
        },
    )
    row = planning.progress(f.request, plan)[1]
    assert Decimal(row["company_coverage"]) == 2000
    assert Decimal(row["remaining"]) == 4000
    assert Decimal(row["remaining_founder_targets"][str(f.a.pk)]) == 2000
    assert Decimal(row["verified_designated"]) == 0
    assert JournalEntry.objects.count() == journals
    with pytest.raises(BusinessRuleViolation):
        planning.cover_from_company(
            f.request,
            {
                "plan_id": plan.pk,
                "bank_id": f.bank.pk,
                "month": "2026-02-01",
                "amount": "5000",
                "reference": "Too much coverage",
            },
        )
    planning.update_company_coverage(f.request, coverage.pk, {"reason": "Revised plan"})
    assert Decimal(planning.progress(f.request, plan)[1]["remaining"]) == 6000


def test_reserve_actual_funding_rollover_partial_consumption_and_release(founder_books):
    f = founder_books
    schedule, _ = setup_plan(f, annual=True)
    reserve = planning.save_reserve(
        f.request,
        {
            "name": "Domain cycle",
            "schedule_id": schedule.pk,
            "starts": "2026-01-01",
            "renewal": "2026-12-01",
            "target": "1200",
        },
    )
    forecast = planning.forecast(f.request, {"starts": "2026-01-01", "months": 12})
    assert Decimal(forecast["rows"][0]["reserve_target"]) == 100
    assert Decimal(forecast["rows"][-1]["founder_request"]) == 1200
    posted = receipt(f, "2000")
    designated = planning.designate(
        f.request,
        {
            "receipt_id": posted.pk,
            "reserve_id": reserve.pk,
            "month": "2026-02-01",
            "amount": "1100",
        },
    )
    forecast = planning.forecast(f.request, {"starts": "2026-01-01", "months": 12})
    assert Decimal(forecast["rows"][-1]["founder_request"]) == 100
    revised = planning.save_reserve(
        f.request,
        {
            "name": "Repriced domain",
            "schedule_id": schedule.pk,
            "starts": "2026-01-01",
            "renewal": "2026-12-01",
            "target": "1300",
            "previous_id": reserve.pk,
            "reason": "Documented price revision; carry retained funding",
        },
    )
    designated.refresh_from_db()
    assert designated.reserve_id == reserve.pk
    assert designated.transfers.count() == 1
    designated = designated.transfers.get().destination
    assert designated.reserve_id == revised.pk
    paid = payables.save_expense(
        f.request,
        {
            "description": "Early domain renewal",
            "currency": "BDT",
            "expense_date": "2026-03-01",
            "account_id": f.accounts["5100"].pk,
            "amount": "800",
            "payment_mode": "paid",
            "bank_account_id": f.bank.pk,
        },
    )
    paid.recurring_schedule = schedule
    paid.save(update_fields=["recurring_schedule"])
    paid = payables.post_expense(f.request, paid.pk)
    before = JournalEntry.objects.count()
    planning.consume(f.request, designated.pk, paid.pk, "600")
    assert planning.reserve_stats(revised)["consumed"] == Decimal("600")
    assert planning.reserve_stats(revised)["designated"] == Decimal("500")
    assert JournalEntry.objects.count() == before
    with pytest.raises(BusinessRuleViolation):
        payables.void_expense(f.request, paid.pk, "Needs corrected amount")
    consumption = FundingConsumption.objects.get(designation=designated)
    with pytest.raises(IntegrityError), transaction.atomic():
        FundingConsumption.objects.filter(pk=consumption.pk).update(amount="1")
    planning.reverse_consumption(
        f.request, consumption.pk, "Release before correcting source payment"
    )
    assert planning.reserve_stats(revised)["consumed"] == 0
    assert planning.reserve_stats(revised)["designated"] == 1100
    payables.void_expense(f.request, paid.pk, "Correction after releasing allocation")


def test_plan_snapshot_stays_frozen_and_empty_corporate_history_remains_empty(founder_books):
    f = founder_books
    schedule, plan = setup_plan(f)
    before = plan.snapshot
    schedule.template = {**schedule.template, "amount": "9000"}
    schedule.save(update_fields=["template"])
    refreshed = planning.forecast(f.request, {"starts": "2026-01-01", "months": 12})
    plan.refresh_from_db()
    assert plan.snapshot == before
    assert Decimal(refreshed["rows"][0]["cost"]) == 9000
    assert not CorporateTransaction.objects.exists()
    assert not JournalEntry.objects.exists()


def test_posted_transaction_cannot_escape_immutability_by_resetting_state(founder_books):
    tx = receipt(founder_books)
    with pytest.raises(IntegrityError), transaction.atomic():
        CorporateTransaction.objects.filter(pk=tx.pk).update(status="recorded")


def test_effective_40_40_20_policy_changes_new_forecasts_without_rewriting_prior_snapshots(
    founder_books,
):
    from datetime import date

    f = founder_books
    schedule, saved = setup_plan(f)
    third = FinancialParty.objects.create(
        name="March partner", kind="individual", joined=date(2026, 3, 1), is_founder=True
    )
    policy = sharing.save_policy(
        f.request,
        {
            "name": "Three founders",
            "basis": "custom",
            "effective_from": "2026-03-01",
            "weights": {str(f.a.pk): "40", str(f.b.pk): "40", str(third.pk): "20"},
        },
    )
    sharing.activate(f.request, policy.pk)
    recurring.save_schedule(
        f.request,
        {
            "name": "Annual renewal",
            "vendor_id": schedule.vendor_id,
            "currency": "BDT",
            "frequency": "yearly",
            "interval": 1,
            "start_date": "2026-12-01",
            "description": "Annual renewal",
            "account_id": f.accounts["5100"].pk,
            "amount": "1200",
            "payment_mode": "accrued",
        },
    )
    rows = planning.forecast(f.request, {"starts": "2026-01-01", "months": 12})["rows"]
    assert Decimal(rows[0]["founders"][str(f.a.pk)]) == 3000
    assert {pk: Decimal(value) for pk, value in rows[2]["founders"].items()} == {
        str(f.a.pk): Decimal("2400"),
        str(f.b.pk): Decimal("2400"),
        str(third.pk): Decimal("1200"),
    }
    assert {pk: Decimal(value) for pk, value in rows[11]["founders"].items()} == {
        str(f.a.pk): Decimal("2880"),
        str(f.b.pk): Decimal("2880"),
        str(third.pk): Decimal("1440"),
    }
    saved.refresh_from_db()
    assert str(third.pk) not in saved.snapshot["rows"][2]["founders"]


def test_partially_consumed_cycle_rolls_only_surplus_without_moving_its_payment_history(
    founder_books,
    client_for,
):
    from apps.founders.models import FundingRelease

    f = founder_books
    schedule, _ = setup_plan(f, annual=True)
    old = planning.save_reserve(
        f.request,
        {
            "name": "Original annual cycle",
            "schedule_id": schedule.pk,
            "starts": "2026-01-01",
            "renewal": "2026-12-01",
            "target": "1200",
        },
    )
    cash = receipt(f, "1200")
    funding = planning.designate(
        f.request,
        {
            "receipt_id": cash.pk,
            "reserve_id": old.pk,
            "month": "2026-02-01",
            "amount": "1200",
        },
    )
    paid = payables.save_expense(
        f.request,
        {
            "description": "Discounted early renewal",
            "currency": "BDT",
            "expense_date": "2026-03-01",
            "account_id": f.accounts["5100"].pk,
            "amount": "800",
            "payment_mode": "paid",
            "bank_account_id": f.bank.pk,
        },
    )
    paid.recurring_schedule = schedule
    paid.save(update_fields=["recurring_schedule"])
    paid = payables.post_expense(f.request, paid.pk)
    planning.consume(f.request, funding.pk, paid.pk, "800")
    journals = JournalEntry.objects.count()
    new = planning.save_reserve(
        f.request,
        {
            "name": "Next annual cycle",
            "schedule_id": schedule.pk,
            "starts": "2027-01-01",
            "renewal": "2027-12-01",
            "target": "1200",
            "previous_id": old.pk,
            "reason": "Authorized rollover of actual unused surplus only",
        },
    )
    funding.refresh_from_db()
    assert funding.reserve_id == old.pk
    assert FundingConsumption.objects.get(designation=funding).expense_id == paid.pk
    assert planning.reserve_stats(old)["consumed"] == 800
    old.refresh_from_db()
    assert planning.reserve_stats(old)["shortfall"] == 0
    assert planning.reserve_stats(old)["designated"] == 0
    assert planning.reserve_stats(new)["designated"] == 400
    response = client_for(f.request.user).get(f"/api/v1/founders/reserves/{new.pk}/")
    assert response.status_code == 200
    assert isinstance(response.json()["progress"]["designated"], str)
    assert planning.reserve_stats(new)["usable"] == 400
    assert JournalEntry.objects.count() == journals
    target = funding.transfers.get().destination
    released = planning.release_funding(
        f.request, target.pk, "150", "Retained funds reallocated", "release-idempotent-0001"
    )
    assert (
        planning.release_funding(
            f.request, target.pk, "150", "Retained funds reallocated", "release-idempotent-0001"
        ).pk
        == released.pk
    )
    assert planning.retained(type(target).objects.filter(pk=target.pk)) == 250
    with pytest.raises(BusinessRuleViolation):
        planning.release_funding(f.request, target.pk, "300", "Too much", "release-idempotent-0002")
    with pytest.raises(IntegrityError), transaction.atomic():
        FundingRelease.objects.filter(pk=released.pk).update(amount="1")
    planning.designate(
        f.request,
        {
            "receipt_id": cash.pk,
            "reserve_id": new.pk,
            "month": "2027-02-01",
            "amount": "150",
        },
    )
    assert planning.reserve_stats(new)["designated"] == 400
