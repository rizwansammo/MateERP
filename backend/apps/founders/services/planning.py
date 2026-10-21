"""Frozen cost forecasts and evidence-backed funding designations, never GL postings."""

from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from apps.accounting.money import ZERO, convert, strings
from apps.accounting.services.posting import bank_position
from apps.accounting.services.setup import lock_company, rate_for
from apps.accounts.authorization import require
from apps.audit.services import record
from apps.billing.services.recurring import add_period
from apps.core.exceptions import BusinessRuleViolation
from apps.purchasing.models import Expense, RecurringExpenseSchedule, VendorBill
from apps.sales import calculation

from ..models import (
    AnnualReserve,
    CompanyFundingCoverage,
    CorporateTransaction,
    FundingConsumption,
    FundingDesignation,
    FundingPlan,
    FundingPledge,
    FundingRelease,
    ReserveDesignationTransfer,
)
from .common import enabled, on_date, party, positive, split, total
from .sharing import policy_on, weights_on


def month_start(on):
    return on.replace(day=1)


def active_consumptions():
    return FundingConsumption.objects.filter(reverses__isnull=True, reversal__isnull=True)


def allocated(designations):
    return total(designations) - total(FundingRelease.objects.filter(designation__in=designations))


def retained(designations):
    return allocated(designations) - total(
        active_consumptions().filter(designation__in=designations)
    )


def cash_holds(bank):
    return retained(
        FundingDesignation.objects.filter(receipt__bank=bank, receipt__status="posted")
    ) + total(CompanyFundingCoverage.objects.filter(bank=bank, status="active"))


def matches_forecast_expense(plan, on, expense):
    from apps.purchasing.models import RecurringExpenseRun

    for row in plan.snapshot["rows"]:
        if row["month"] != str(on) or row["currency"] != expense.currency:
            continue
        for source in row["sources"]:
            if source.get("expense_id") == expense.pk:
                return True
            if (
                source.get("schedule_id")
                and RecurringExpenseRun.objects.filter(
                    schedule_id=source["schedule_id"],
                    expense=expense,
                    occurrence_date=source["date"],
                ).exists()
            ):
                return True
    return False


def occurrences(schedule, start, end):
    """All occurrence identities, including those already drafted/posted.

    Execution's due_occurrences intentionally omits completed occurrences; a
    forecast must join them, so reuse its date rule without that exclusion.
    """
    for index in range(10_000):
        on = add_period(schedule.start_date, schedule.frequency, schedule.interval, index)
        if on >= end or (schedule.end_date and on > schedule.end_date):
            break
        if on >= start:
            yield on
    else:
        raise BusinessRuleViolation("The schedule exceeds the bounded forecast horizon.")


def reserve_stats(reserve):
    designated = reserve.designations.select_related("receipt__bank")
    remaining = retained(designated.filter(receipt__status="posted"))
    consumed = total(active_consumptions().filter(designation__in=designated))
    released = total(FundingRelease.objects.filter(designation__in=designated))
    coverage = ZERO
    for bank_id in set(designated.values_list("receipt__bank_id", flat=True)):
        from apps.banking.models import BankAccount

        bank = BankAccount.objects.get(pk=bank_id)
        actual, _ = bank_position(bank.gl_account_id)
        all_reserved = cash_holds(bank)
        this_reserved = retained(designated.filter(receipt__bank=bank, receipt__status="posted"))
        # A designation is a plan, not a bank balance or an assertion that a
        # later unrelated payment could not spend the same bank funds.
        coverage += min(this_reserved, max(ZERO, actual - (all_reserved - this_reserved)))
    return {
        "designated": remaining,
        "usable": coverage,
        "consumed": consumed,
        "released": released,
        "shortfall": max(
            ZERO,
            reserve.target
            - coverage
            - consumed
            - (released if reserve.status == "superseded" else ZERO),
        ),
        "cash_shortfall": remaining - coverage,
        "surplus": max(ZERO, remaining + consumed - reserve.target),
    }


@transaction.atomic
def cover_from_company(request, data):
    enabled()
    require(request.user, "founder.planning.manage", "finance.view")
    lock_company()
    from apps.banking.models import BankAccount

    plan = get_object_or_404(FundingPlan, pk=data["plan_id"])
    bank = (
        BankAccount.objects.select_for_update().filter(pk=data["bank_id"], is_active=True).first()
    )
    on = month_start(on_date(data["month"]))
    if not bank or plan.mode != "partial":
        raise ValidationError(
            {"plan_id": "Choose a partial-funding plan and an active company account."}
        )
    row = next(
        (
            r
            for r in plan.snapshot["rows"]
            if r["month"] == str(on) and r["currency"] == bank.currency
        ),
        None,
    )
    if not row:
        raise ValidationError({"month": "The forecast has no matching month and currency."})
    value = positive(data["amount"], bank.currency)
    coverage = total(
        plan.company_coverage.filter(month=on, bank__currency=bank.currency).exclude(
            status="released"
        )
    )
    if value + coverage > Decimal(row["funding_target"]):
        raise BusinessRuleViolation("Company coverage exceeds this month's funding requirement.")
    cash, _ = bank_position(bank.gl_account_id)
    reserved = cash_holds(bank)
    if reserved + value > cash:
        raise BusinessRuleViolation(
            "Posted bank funds do not cover this allocation after existing designations."
        )
    obj = CompanyFundingCoverage.objects.create(
        plan=plan,
        bank=bank,
        month=on,
        amount=value,
        reference=data["reference"],
        created_by=request.user,
    )
    record(
        "founder.company_funding_allocated",
        request=request,
        target=obj,
        after={"plan": plan.pk, "amount": value, "bank": bank.pk},
        reason=obj.reference,
    )
    return obj


@transaction.atomic
def update_company_coverage(request, pk, data):
    enabled()
    require(request.user, "founder.planning.manage", "finance.view")
    lock_company()
    obj = CompanyFundingCoverage.objects.select_for_update().get(pk=pk)
    if obj.status == "released" or (obj.status != "active" and data.get("expense_id")):
        raise BusinessRuleViolation(
            "This funding allocation has already been consumed or released."
        )
    if data.get("expense_id"):
        expense = get_object_or_404(Expense, pk=data["expense_id"])
        if (
            expense.status != "paid"
            or expense.payment_mode != "paid"
            or expense.bank_account_id != obj.bank_id
        ):
            raise ValidationError(
                {"expense_id": "Select the actual company-paid expense from this bank."}
            )
        if not matches_forecast_expense(obj.plan, obj.month, expense):
            raise ValidationError({"expense_id": "This expense does not fulfill this forecast."})
        covered = total(active_consumptions().filter(expense=expense)) + total(
            expense.company_funding_coverage.filter(status="consumed")
        )
        if covered + obj.amount > expense.total:
            raise BusinessRuleViolation("This expense has insufficient uncovered cost.")
        obj.expense, obj.status = expense, "consumed"
    else:
        if not data.get("reason", "").strip():
            raise ValidationError({"reason": "Explain releasing the company-funding designation."})
        obj.status = "released"
    obj.save(update_fields=["status", "expense"])
    record(
        "founder.company_funding_updated",
        request=request,
        target=obj,
        after={"status": obj.status, "expense": obj.expense_id},
        reason=data.get("reason", ""),
    )
    return obj


def company_coverage(plan, on, currency):
    coverage = ZERO
    for obj in (
        plan.company_coverage.filter(month=on, bank__currency=currency)
        .exclude(status="released")
        .select_related("bank")
    ):
        if obj.status == "consumed":
            coverage += obj.amount
        else:
            cash, _ = bank_position(obj.bank.gl_account_id)
            other = cash_holds(obj.bank) - obj.amount
            coverage += min(obj.amount, max(ZERO, cash - other))
    return coverage


def posted_costs(row, base_currency):
    """Compare only fulfilled source identities with their frozen estimates.

    Historical base totals come from the owning posted source, never today's
    FX rate or a conversion of bank carrying value. Unfulfilled costs are not
    reported as a favorable variance.
    """
    from apps.purchasing.models import RecurringExpenseRun

    sources = row["sources"]
    expenses = {
        obj.pk: obj for obj in Expense.objects.filter(pk__in=[s.get("expense_id") for s in sources])
    }
    runs = {
        (obj.schedule_id, str(obj.occurrence_date)): obj.expense
        for obj in RecurringExpenseRun.objects.filter(
            schedule_id__in=[s.get("schedule_id") for s in sources],
            occurrence_date__in=[s["date"] for s in sources],
        ).select_related("expense")
    }
    bills = {
        str(obj.pk): obj
        for obj in VendorBill.objects.filter(
            pk__in=[
                s["identity"].split(":")[1] for s in sources if s["identity"].startswith("bill:")
            ]
        )
    }
    result = []
    for source in sources:
        obj = (
            expenses.get(source.get("expense_id"))
            or runs.get((source.get("schedule_id"), source["date"]))
            or bills.get(source["identity"].removeprefix("bill:"))
        )
        if (
            obj is None
            or obj.base_total is None
            or obj.status not in {"posted", "partially_paid", "paid"}
        ):
            continue
        estimate = (
            convert(Decimal(source["cost"]), Decimal(row["estimated_rate"]), base_currency)
            if row.get("estimated_rate")
            else None
        )
        result.append(
            {
                "identity": source["identity"],
                "name": source["name"],
                "journal_id": obj.journal_id,
                "actual_rate": obj.exchange_rate,
                "actual_base_cost": obj.base_total,
                "estimated_base_cost": estimate,
                "base_cost_variance": obj.base_total - estimate if estimate is not None else None,
            }
        )
    return {"base_currency": base_currency, "posted_costs": result}


@transaction.atomic
def progress(request, plan):
    """Read actual funding under the same company lock used by allocations.

    A pledge is disclosed separately. Only posted receipts can satisfy a
    founder target, and retained cash is still checked against the real bank.
    """
    enabled()
    require(request.user, "founder.planning.manage")
    lock_company()
    result = []
    for row in plan.snapshot["rows"]:
        allocations = plan.designations.filter(
            month=row["month"], receipt__currency=row["currency"], receipt__status="posted"
        )
        funded = allocated(allocations)
        company = company_coverage(plan, row["month"], row["currency"])
        remaining = max(ZERO, Decimal(row["founder_request"]) - company)
        weights = {k: v for k, v in row["founders"].items() if Decimal(v) > ZERO}
        targets = (
            split(remaining, row["currency"], weights)
            if remaining and weights
            else {k: ZERO for k in row["founders"]}
        )
        verified = {k: allocated(allocations.filter(receipt__party_id=k)) for k in row["founders"]}
        result.append(
            {
                **row,
                **posted_costs(row, plan.snapshot["base_currency"]),
                "verified_designated": funded,
                "company_coverage": company,
                "remaining_founder_targets": targets,
                "verified_by_founder": verified,
                "remaining_by_founder": {k: max(ZERO, v - verified[k]) for k, v in targets.items()},
                "surplus_by_founder": {k: max(ZERO, verified[k] - v) for k, v in targets.items()},
                "remaining": max(ZERO, remaining - funded),
                "pledges": list(
                    plan.pledges.filter(month=row["month"], currency=row["currency"]).values(
                        "id", "party_id", "amount", "status", "reference"
                    )
                ),
            }
        )
    return strings(result)


def _estimated(schedule, on):
    template = schedule.template
    result = calculation.calculate(
        currency=schedule.currency,
        on=on,
        prices_include_tax=bool(template.get("prices_include_tax")),
        lines=[
            {
                "quantity": "1",
                "unit_price": template["amount"],
                "tax_code_id": template.get("tax_code_id"),
            }
        ],
    )
    return result["total"]


def _source_rows(data, start, end):
    rows = []
    schedules = RecurringExpenseSchedule.objects.all().prefetch_related("runs__expense")
    if "schedule_ids" in data:
        schedules = schedules.filter(pk__in=data["schedule_ids"])
    for schedule in schedules:
        runs = {run.occurrence_date: run for run in schedule.runs.all()}
        for on in occurrences(schedule, start, end):
            run = runs.get(on)
            expense = run.expense if run and run.expense_id else None
            if expense and expense.status in {"void", "cancelled"}:
                continue
            if not expense and schedule.status != "active":
                continue
            value = expense.total if expense else _estimated(schedule, on)
            due = value
            if expense:
                due = (
                    expense.outstanding
                    if expense.payment_mode == "accrued"
                    and expense.status in {"posted", "partially_paid", "paid"}
                    else ZERO
                    if expense.status == "paid"
                    else value
                )
            rows.append(
                {
                    "identity": f"schedule:{schedule.pk}:{on}",
                    "date": on,
                    "currency": schedule.currency,
                    "cost": value,
                    "cash_due": due,
                    "category": expense.account_id
                    if expense
                    else schedule.template.get("account_id"),
                    "expense_id": expense.pk if expense else None,
                    "schedule_id": schedule.pk,
                    "source_revision": schedule.revision,
                    "source_template": schedule.template,
                    "name": schedule.name,
                    "state": expense.status if expense else "estimated",
                }
            )
    for source in Expense.objects.filter(
        pk__in=data.get("expense_ids", []), recurring_schedule__isnull=True
    ):
        if not start <= source.expense_date < end or source.status in {"void", "cancelled"}:
            continue
        due = (
            source.outstanding
            if source.payment_mode == "accrued" and source.status != "draft"
            else ZERO
            if source.status == "paid"
            else source.total
        )
        rows.append(
            {
                "identity": f"expense:{source.pk}",
                "date": source.expense_date,
                "currency": source.currency,
                "cost": source.total,
                "cash_due": due,
                "category": source.account_id,
                "expense_id": source.pk,
                "name": source.description,
                "state": source.status,
            }
        )
    for source in VendorBill.objects.filter(pk__in=data.get("bill_ids", [])):
        if start <= source.due_date < end and source.status in {
            "draft",
            "awaiting_approval",
            "posted",
            "partially_paid",
            "paid",
        }:
            rows.append(
                {
                    "identity": f"bill:{source.pk}",
                    "date": source.due_date,
                    "currency": source.currency,
                    "cost": source.total,
                    "cash_due": source.outstanding,
                    "category": None,
                    "name": source.vendor_reference,
                    "state": source.status,
                }
            )
    return rows


@transaction.atomic
def forecast(request, data, *, save=False):
    enabled()
    require(request.user, "founder.planning.manage")
    company = lock_company()
    start = month_start(on_date(data["starts"]))
    count = data.get("months", 12)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 24:
        raise ValidationError({"months": "Choose 1–24 months."})
    end = add_period(start, "monthly", 1, count)
    mode = data.get("mode", "founders")
    if mode not in {"founders", "partial", "self_sustaining"}:
        raise ValidationError({"mode": "Choose founders, partial or self_sustaining."})
    source_rows = _source_rows(data, start, end)
    cells, issues = {}, []

    def cell(on, currency):
        return cells.setdefault(
            (month_start(on), currency),
            {
                "month": month_start(on),
                "currency": currency,
                "cost": ZERO,
                "cash_due": ZERO,
                "reserve_target": ZERO,
                "reserve_coverage": ZERO,
                "funding_target": ZERO,
                "founders": {},
                "sources": [],
            },
        )

    for source in source_rows:
        row = cell(source["date"], source["currency"])
        row["cost"] += source["cost"]
        row["cash_due"] += source["cash_due"]
        row["funding_target"] += source["cash_due"]
        row["sources"].append(source)
        try:
            policy = policy_on(source["date"], source["category"])
            allocations = split(
                source["cash_due"], source["currency"], weights_on(policy, source["date"])
            )
            source["policy_id"], source["weights"] = policy.pk, weights_on(policy, source["date"])
            for pk, value in allocations.items():
                row["founders"][pk] = row["founders"].get(pk, ZERO) + value
        except BusinessRuleViolation as exc:
            issues.append({"source": source["identity"], "message": str(exc.detail)})
    reserves = AnnualReserve.objects.filter(status="active", starts__lt=end, renewal__gte=start)
    if "schedule_ids" in data:
        reserves = reserves.filter(schedule_id__in=data["schedule_ids"])
    for reserve in reserves:
        stats = reserve_stats(reserve)
        cycle_months = (
            (reserve.renewal.year - reserve.starts.year) * 12
            + reserve.renewal.month
            - reserve.starts.month
            + 1
        )
        monthly_amounts = split(
            reserve.target, reserve.currency, {str(i + 1): "1" for i in range(cycle_months)}
        )
        for index in range(cycle_months):
            on = add_period(month_start(reserve.starts), "monthly", 1, index)
            if not start <= on < end:
                continue
            row = cell(on, reserve.currency)
            amount = monthly_amounts[str(index + 1)]
            if on == month_start(reserve.renewal):
                # Remove the due occurrence target and replace it with its
                # actual unfunded remainder. Never add another installment.
                matching = [
                    s
                    for s in row["sources"]
                    if s.get("schedule_id") == reserve.schedule_id and s["date"] == reserve.renewal
                ]
                if not matching:
                    issues.append(
                        {
                            "source": f"reserve:{reserve.pk}",
                            "message": "The renewal does not match a forecast schedule occurrence.",
                        }
                    )
                    continue
                old = sum((s["cash_due"] for s in matching), ZERO)
                need = max(ZERO, old - stats["usable"])
                delta = need - old
                row["reserve_coverage"] += min(old, stats["usable"])
                row["funding_target"] += delta
                weights = matching[0].get("weights") or weights_on(reserve.policy, reserve.renewal)
                for pk, value in split(abs(delta), reserve.currency, weights).items():
                    row["founders"][pk] = row["founders"].get(pk, ZERO) - value
            else:
                row["reserve_target"] += amount
                row["funding_target"] += amount
                weights = weights_on(policy_on(on, reserve.schedule.template.get("account_id")), on)
                for pk, value in split(amount, reserve.currency, weights).items():
                    row["founders"][pk] = row["founders"].get(pk, ZERO) + value
    currencies = {currency for _, currency in cells} or {company.base_currency}
    for index in range(count):
        for currency in currencies:
            cell(add_period(start, "monthly", 1, index), currency)
    for row in cells.values():
        if mode == "self_sustaining":
            row["founders"] = {k: ZERO for k in row["founders"]}
            row["founder_request"] = ZERO
        else:
            row["founder_request"] = row["funding_target"]
        try:
            rate, source = rate_for(row["currency"], row["month"], company.base_currency)
            row["estimated_rate"], row["rate_source"] = rate, source
            row["estimated_base_cost"] = convert(row["cost"], rate, company.base_currency)
        except (BusinessRuleViolation, ValidationError) as exc:
            row["estimated_base_cost"] = None
            issues.append({"source": str(row["month"]), "message": str(exc.detail)})
    snapshot = strings(
        {
            "base_currency": company.base_currency,
            "starts": start,
            "months": count,
            "mode": mode,
            "rows": sorted(cells.values(), key=lambda row: (row["month"], row["currency"])),
            "issues": issues,
            "complete": not issues,
            "inputs": data,
        }
    )
    if not save:
        return snapshot
    obj = FundingPlan.objects.create(
        name=data["name"],
        starts=start,
        months=count,
        mode=mode,
        snapshot=snapshot,
        previous_id=data.get("previous_id"),
        created_by=request.user,
    )
    record(
        "founder.forecast_saved",
        request=request,
        target=obj,
        after={"starts": str(start), "months": count, "complete": not issues},
    )
    return obj


@transaction.atomic
def save_reserve(request, data):
    enabled()
    require(request.user, "founder.planning.manage")
    lock_company()
    schedule = get_object_or_404(RecurringExpenseSchedule, pk=data["schedule_id"])
    start, renewal = on_date(data["starts"]), on_date(data["renewal"])
    if (
        not start <= renewal
        or (renewal.year - start.year) * 12 + renewal.month - start.month >= 100
    ):
        raise ValidationError({"renewal": "Choose a reserve period between one and 100 months."})
    end = add_period(renewal, "monthly", 1, 1)
    if renewal not in set(occurrences(schedule, renewal, end)):
        raise ValidationError({"renewal": "Use an actual schedule renewal date."})
    policy = policy_on(start)
    previous = AnnualReserve.objects.select_for_update().filter(pk=data.get("previous_id")).first()
    if previous:
        if previous.status != "active":
            raise BusinessRuleViolation(
                "Revise the active reserve version; earlier cycles stay retained."
            )
        if previous.schedule_id != schedule.pk:
            raise ValidationError({"previous_id": "A revision must retain the recurring schedule."})
        if (
            active_consumptions().filter(designation__reserve=previous).exists()
            and renewal <= previous.renewal
        ):
            raise BusinessRuleViolation(
                "A consumed cycle stays retained; roll its unused surplus into a later renewal."
            )
        previous.status = "superseded"
        previous.save(update_fields=["status"])
    obj = AnnualReserve(
        name=data["name"],
        schedule=schedule,
        starts=start,
        renewal=renewal,
        currency=schedule.currency,
        target=positive(data["target"], schedule.currency),
        policy=policy,
        previous=previous,
        snapshot=strings(
            {"weights": weights_on(policy, start), "schedule_revision": schedule.revision}
        ),
        created_by=request.user,
    )
    obj.full_clean()
    obj.save()
    if previous:
        reason = data.get("reason", "")
        if previous.designations.exists() and not reason.strip():
            raise ValidationError(
                {"reason": "Explain the explicitly authorized rollover of retained reserve funds."}
            )
        if obj.currency != previous.currency:
            raise BusinessRuleViolation("Reserve rollover cannot silently convert currencies.")
        for designation in previous.designations.select_for_update():
            value = retained(FundingDesignation.objects.filter(pk=designation.pk))
            if not value:
                continue
            release_funding(
                request,
                designation.pk,
                value,
                reason,
                f"reserve-rollover:{obj.pk}:{designation.pk}",
            )
            destination = designate(
                request,
                {
                    "receipt_id": designation.receipt_id,
                    "reserve_id": obj.pk,
                    "month": str(month_start(obj.starts)),
                    "amount": value,
                },
            )
            ReserveDesignationTransfer.objects.create(
                designation=designation,
                destination=destination,
                amount=value,
                previous_reserve=previous,
                new_reserve=obj,
                reason=reason,
                actor=request.user,
            )
    record(
        "founder.reserve_created",
        request=request,
        target=obj,
        after={"target": obj.target, "renewal": str(renewal)},
    )
    return obj


@transaction.atomic
def pledge(request, data):
    enabled()
    require(request.user, "founder.planning.manage")
    lock_company()
    plan = get_object_or_404(FundingPlan, pk=data["plan_id"])
    participant = party(data["party_id"], founder=True)
    if data.get("status", "requested") not in {"requested", "promised", "cancelled"}:
        raise ValidationError({"status": "Pledges are requests/promises, never verified receipts."})
    obj = FundingPledge.objects.create(
        plan=plan,
        party=participant,
        month=month_start(on_date(data["month"])),
        currency=data["currency"],
        amount=positive(data["amount"], data["currency"]),
        status=data.get("status", "requested"),
        reference=data.get("reference", ""),
    )
    record(
        "founder.funding_pledged",
        request=request,
        target=obj,
        after={"amount": obj.amount, "status": obj.status},
    )
    return obj


@transaction.atomic
def pledge_status(request, pk, status, reason):
    enabled()
    require(request.user, "founder.planning.manage")
    lock_company()
    obj = get_object_or_404(FundingPledge.objects.select_for_update(), pk=pk)
    if status not in {"promised", "cancelled"} or not reason.strip():
        raise ValidationError({"reason": "Explain the promise or cancellation."})
    if obj.status == "cancelled" or (obj.status == "promised" and status != "cancelled"):
        raise BusinessRuleViolation("This request has already reached this or a later status.")
    before = obj.status
    obj.status = status
    obj.save(update_fields=["status"])
    record(
        "founder.funding_pledge_updated",
        request=request,
        target=obj,
        before={"status": before},
        after={"status": status},
        reason=reason,
    )
    return obj


@transaction.atomic
def designate(request, data):
    enabled()
    require(request.user, "founder.planning.manage")
    lock_company()
    receipt = (
        CorporateTransaction.objects.select_for_update()
        .filter(pk=data["receipt_id"], kind="receipt", status="posted")
        .first()
    )
    if not receipt:
        raise ValidationError({"receipt_id": "Select a verified posted company receipt."})
    amount = positive(data["amount"], receipt.currency)
    if allocated(receipt.designations.all()) + amount > receipt.amount:
        raise BusinessRuleViolation("This receipt has insufficient undesignated funding.")
    bank = receipt.bank
    position, _ = bank_position(bank.gl_account_id)
    reserved = cash_holds(bank)
    if amount + reserved > position:
        raise BusinessRuleViolation("Current posted bank funds do not cover this designation.")
    if bool(data.get("plan_id")) == bool(data.get("reserve_id")):
        raise ValidationError({"target": "Select one plan or reserve."})
    reserve = (
        get_object_or_404(AnnualReserve, pk=data["reserve_id"]) if data.get("reserve_id") else None
    )
    plan = get_object_or_404(FundingPlan, pk=data["plan_id"]) if data.get("plan_id") else None
    on = month_start(on_date(data["month"]))
    if reserve and (
        reserve.status != "active"
        or reserve.currency != receipt.currency
        or not month_start(reserve.starts) <= on <= month_start(reserve.renewal)
    ):
        raise ValidationError(
            {"reserve_id": "Select an active reserve in the receipt currency and cycle."}
        )
    if plan and not any(
        row["month"] == str(on) and row["currency"] == receipt.currency
        for row in plan.snapshot["rows"]
    ):
        raise ValidationError({"plan_id": "The plan has no matching month/currency."})
    obj = FundingDesignation.objects.create(
        receipt=receipt,
        plan=plan,
        reserve=reserve,
        month=on,
        amount=amount,
        created_by=request.user,
    )
    record(
        "founder.funding_designated",
        request=request,
        target=obj,
        after={"receipt": receipt.pk, "amount": amount},
    )
    return obj


@transaction.atomic
def consume(request, pk, expense_id, amount=None):
    enabled()
    require(request.user, "founder.planning.manage")
    lock_company()
    obj = (
        FundingDesignation.objects.select_for_update(of=("self",))
        .select_related("receipt", "reserve")
        .get(pk=pk)
    )
    expense = get_object_or_404(Expense, pk=expense_id)
    existing = active_consumptions().filter(designation=obj, expense=expense).first()
    if existing:
        if amount is not None and positive(amount, obj.receipt.currency) != existing.amount:
            raise BusinessRuleViolation("The existing consumption has a different amount.")
        return obj
    if (
        expense.status != "paid"
        or expense.payment_mode != "paid"
        or expense.bank_account_id != obj.receipt.bank_id
        or expense.currency != obj.receipt.currency
    ):
        raise ValidationError(
            {
                "expense_id": "Select the actual posted company-bank payment "
                "in the designated currency/account."
            }
        )
    if obj.plan_id and not matches_forecast_expense(obj.plan, obj.month, expense):
        raise ValidationError({"expense_id": "This expense does not fulfill this forecast."})
    if obj.reserve_id and expense.recurring_schedule_id != obj.reserve.schedule_id:
        raise ValidationError({"expense_id": "The expense must belong to this renewal schedule."})
    remaining = retained(FundingDesignation.objects.filter(pk=obj.pk))
    value = positive(amount, obj.receipt.currency) if amount is not None else remaining
    covered = total(active_consumptions().filter(expense=expense)) + total(
        expense.company_funding_coverage.filter(status="consumed")
    )
    if value <= ZERO or value > remaining or covered + value > expense.total:
        raise BusinessRuleViolation("This expense is already covered by designated funding.")
    if obj.reserve_id:
        if (
            month_start(expense.expense_date) > month_start(obj.reserve.renewal)
            or expense.expense_date < obj.reserve.starts
        ):
            raise ValidationError(
                {
                    "expense_id": "Link a payment within this reserve cycle, "
                    "including an early renewal."
                }
            )
        from apps.purchasing.models import RecurringExpenseRun

        run = RecurringExpenseRun.objects.filter(expense=expense).first()
        if run and run.occurrence_date != obj.reserve.renewal:
            raise BusinessRuleViolation("This payment belongs to a different renewal occurrence.")
    FundingConsumption.objects.create(
        designation=obj, expense=expense, amount=value, created_by=request.user
    )
    record(
        "founder.reserve_consumed",
        request=request,
        target=obj,
        after={"expense": expense.pk, "amount": value},
    )
    return obj


@transaction.atomic
def release_funding(request, pk, amount, reason, client_key):
    """Release retained planning funds without reversing cash or prior use."""
    enabled()
    require(request.user, "founder.planning.manage")
    lock_company()
    from .corporate import _key

    _key(client_key)
    obj = get_object_or_404(FundingDesignation.objects.select_for_update(), pk=pk)
    value = positive(amount, obj.receipt.currency)
    previous = FundingRelease.objects.filter(client_key=client_key).first()
    if previous:
        if (
            previous.designation_id != obj.pk
            or previous.amount != value
            or previous.reason != reason
        ):
            raise BusinessRuleViolation(
                "This release key belongs to different content.", code="idempotency_conflict"
            )
        return previous
    if not reason.strip() or value > retained(FundingDesignation.objects.filter(pk=obj.pk)):
        raise BusinessRuleViolation("Release only unused retained funds with an explicit reason.")
    released = FundingRelease.objects.create(
        designation=obj,
        amount=value,
        reason=reason,
        client_key=client_key,
        created_by=request.user,
    )
    record(
        "founder.retained_funding_released",
        request=request,
        target=released,
        after={"designation": obj.pk, "amount": value},
        reason=reason,
    )
    return released


@transaction.atomic
def reverse_consumption(request, pk, reason):
    enabled()
    require(request.user, "founder.planning.manage")
    lock_company()
    obj = active_consumptions().select_for_update(of=("self",)).get(pk=pk)
    if not reason.strip():
        raise ValidationError({"reason": "Explain releasing this cost allocation."})
    reversal = FundingConsumption.objects.create(
        designation=obj.designation,
        expense=obj.expense,
        amount=obj.amount,
        reverses=obj,
        reason=reason,
        created_by=request.user,
    )
    record("founder.funding_consumption_reversed", request=request, target=reversal, reason=reason)
    return reversal
