"""Recurring expenses and subscriptions: schedules generate draft expenses for review.

Same occurrence model as recurring billing: unique per schedule and date, catch-up in
date order, triggered by a user or ``manage.py run_recurring``. Drafts are never posted
automatically; renewals approaching within the reminder window are listed as upcoming.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import get_permission_codes, require
from apps.audit.services import record
from apps.billing.services import common
from apps.billing.services.recurring import add_period
from apps.core.exceptions import BusinessRuleViolation
from apps.sales.services import enabled_currency

from ..models import RecurringExpenseRun as Run
from ..models import RecurringExpenseSchedule as Schedule
from ..models import Vendor
from .payables import save_expense

MAX_CATCH_UP = 36
TEMPLATE_KEYS = (
    "description",
    "account_id",
    "amount",
    "tax_code_id",
    "prices_include_tax",
    "payment_mode",
    "bank_account_id",
    "method",
    "project_id",
    "notes",
)


def due_occurrences(schedule, until):
    if schedule.status != Schedule.Status.ACTIVE:
        return []
    done = set(schedule.runs.exclude(status="failed").values_list("occurrence_date", flat=True))
    out = []
    for index in range(10_000):
        on = add_period(schedule.start_date, schedule.frequency, schedule.interval, index)
        if on > until or (schedule.end_date and on > schedule.end_date) or len(out) >= MAX_CATCH_UP:
            break
        if on not in done:
            out.append(on)
    return out


def next_occurrence(schedule):
    upcoming_dates = due_occurrences(schedule, timezone.localdate() + timedelta(days=3660))
    return upcoming_dates[0] if upcoming_dates else None


@transaction.atomic
def save_schedule(request, data, pk=None):
    require(request.user, "expenses.manage")
    schedule = (
        Schedule.objects.select_for_update().filter(pk=pk).first()
        if pk
        else Schedule(created_by=request.user)
    )
    if pk and schedule is None:
        raise NotFound()
    if pk and schedule.status in (Schedule.Status.CANCELLED, Schedule.Status.COMPLETED):
        raise BusinessRuleViolation("Cancelled or completed schedules cannot be edited.")
    for field in ("name", "frequency", "interval", "start_date", "end_date", "reminder_days"):
        if field in data:
            setattr(schedule, field, data[field])
    if "vendor_id" in data:
        schedule.vendor = Vendor.objects.filter(pk=data["vendor_id"], is_active=True).first()
    if schedule.vendor_id is None:
        raise ValidationError({"vendor_id": "Select an active vendor."})
    schedule.currency = data.get("currency") or schedule.currency or schedule.vendor.currency
    enabled_currency(schedule.currency)
    template = {**schedule.template, **{k: data[k] for k in TEMPLATE_KEYS if k in data}}
    if not template.get("description") or not template.get("amount"):
        raise ValidationError({"amount": "Describe the expense and enter its amount."})
    if template.get("payment_mode") not in ("paid", "accrued"):
        raise ValidationError({"payment_mode": "Choose paid now or accrued."})
    template["amount"] = str(template["amount"])
    schedule.template = template
    if pk:
        schedule.revision += 1
    schedule.full_clean()
    schedule.save()
    schedule.next_run_date = next_occurrence(schedule)
    schedule.save(update_fields=["next_run_date"])
    record(
        "purchasing.schedule_updated" if pk else "purchasing.schedule_created",
        request=request,
        target=schedule,
        after={"name": schedule.name, "frequency": schedule.frequency},
    )
    return schedule


@transaction.atomic
def set_status(request, pk, status):
    require(request.user, "expenses.manage")
    schedule = Schedule.objects.select_for_update().filter(pk=pk).first()
    if schedule is None:
        raise NotFound()
    allowed = {"paused": ("active",), "active": ("paused",), "cancelled": ("active", "paused")}
    if schedule.status not in allowed.get(status, ()):
        raise BusinessRuleViolation(f"A {schedule.status} schedule cannot become {status}.")
    schedule.status = status
    schedule.save(update_fields=["status"])
    record(f"purchasing.schedule_{status}", request=request, target=schedule)
    return schedule


def _expense_data(schedule, on):
    template = schedule.template
    return {
        "vendor_id": schedule.vendor_id,
        "expense_date": on,
        "currency": schedule.currency,
        "description": f"{template['description']} — {on:%b %Y}"[:300],
        "account_id": template.get("account_id"),
        "amount": template["amount"],
        "tax_code_id": template.get("tax_code_id"),
        "prices_include_tax": bool(template.get("prices_include_tax")),
        "payment_mode": template["payment_mode"],
        "bank_account_id": template.get("bank_account_id"),
        "method": template.get("method") or "bank_transfer",
        "project_id": template.get("project_id"),
        "notes": template.get("notes") or "",
    }


def _occurrence(schedule_id, on, runner):
    try:
        with transaction.atomic():
            lock_company()
            schedule = Schedule.objects.select_for_update().get(pk=schedule_id)
            run = (
                Run.objects.select_for_update()
                .filter(schedule=schedule, occurrence_date=on)
                .first()
            )
            if run and run.status != "failed":
                return {
                    "schedule": schedule_id,
                    "date": on,
                    "status": "skipped",
                    "expense": run.expense_id,
                }
            actor = runner or schedule.created_by
            if not actor.is_active or "expenses.manage" not in get_permission_codes(actor):
                raise BusinessRuleViolation("The runner can no longer manage expenses.")
            expense = save_expense(
                common.acting(actor), _expense_data(schedule, on), schedule=schedule
            )
            values = {
                "expense": expense,
                "status": "drafted",
                "message": "Draft created for review.",
                "run_by": actor,
            }
            if run:
                for key, value in values.items():
                    setattr(run, key, value)
                run.save()
            else:
                Run.objects.create(schedule=schedule, occurrence_date=on, **values)
        return {"schedule": schedule_id, "date": on, "status": "drafted", "expense": expense.pk}
    except IntegrityError:
        return {"schedule": schedule_id, "date": on, "status": "skipped", "expense": None}
    except APIException as exc:
        message = str(exc.detail)[:500]
        with transaction.atomic():
            Run.objects.update_or_create(
                schedule_id=schedule_id,
                occurrence_date=on,
                defaults={"status": "failed", "message": message, "expense": None},
            )
        return {"schedule": schedule_id, "date": on, "status": "failed", "message": message}


def run_due(until=None, *, runner=None, schedule_ids=None):
    if runner is not None:
        require(runner, "expenses.manage")
    until = until or timezone.localdate()
    schedules = Schedule.objects.filter(status=Schedule.Status.ACTIVE)
    if schedule_ids:
        schedules = schedules.filter(pk__in=schedule_ids)
    results = []
    for schedule_id in schedules.order_by("pk").values_list("pk", flat=True):
        schedule = Schedule.objects.get(pk=schedule_id)
        for on in due_occurrences(schedule, until):
            results.append(_occurrence(schedule_id, on, runner))
        with transaction.atomic():
            schedule = Schedule.objects.select_for_update().get(pk=schedule_id)
            schedule.next_run_date = next_occurrence(schedule)
            if schedule.next_run_date is None and schedule.end_date:
                schedule.status = Schedule.Status.COMPLETED
            schedule.save(update_fields=["next_run_date", "status"])
    return results


def upcoming(within_days=None):
    """Active schedules whose next occurrence falls inside their reminder window."""
    today = timezone.localdate()
    out = []
    for schedule in Schedule.objects.filter(status=Schedule.Status.ACTIVE).select_related("vendor"):
        nxt = schedule.next_run_date
        window = within_days if within_days is not None else schedule.reminder_days
        if nxt and nxt <= today + timedelta(days=window):
            out.append(schedule)
    return out
