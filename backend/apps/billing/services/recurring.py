"""Recurring billing schedules: preview, run due occurrences, pause/resume/cancel.

Runs are triggered by a user ("Run due now") or by ``manage.py run_recurring`` from an
operating-system scheduler; MateERP has no background worker of its own. Each
occurrence is unique per schedule and date, so repeated or overlapping runs never
create a second invoice. Missed occurrences are caught up in date order.
"""

import calendar
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.accounting.money import decimal
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import get_permission_codes, require
from apps.audit.services import record
from apps.core.exceptions import BusinessRuleViolation
from apps.sales.models import Customer, Project
from apps.sales.services import enabled_currency

from ..models import RecurringInvoiceRun as Run
from ..models import RecurringInvoiceSchedule as Schedule
from . import common
from .invoices import issue_invoice, save_invoice

MAX_CATCH_UP = 36
MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}


def add_period(start: date, frequency: str, interval: int, count: int) -> date:
    """The ``count``-th occurrence after ``start``; month ends clamp (31 Jan → 28/29 Feb)."""
    if frequency == "weekly":
        return start + timedelta(weeks=interval * count)
    months = MONTHS[frequency] * interval * count
    year, month = divmod(start.month - 1 + months, 12)
    year += start.year
    month += 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def due_occurrences(schedule, until):
    """Occurrence dates not yet successfully run, up to ``until``."""
    if schedule.status != Schedule.Status.ACTIVE:
        return []
    done = set(
        schedule.runs.exclude(status=Run.Status.FAILED).values_list("occurrence_date", flat=True)
    )
    out = []
    for index in range(0, 10_000):
        on = add_period(schedule.start_date, schedule.frequency, schedule.interval, index)
        if on > until or (schedule.end_date and on > schedule.end_date) or len(out) >= MAX_CATCH_UP:
            break
        if on not in done:
            out.append(on)
    return out


def _validate_template(customer, data):
    lines = data.get("lines") or []
    if not lines:
        raise ValidationError({"lines": "Add at least one line to the template."})
    return {
        "lines": [
            {
                k: line.get(k)
                for k in (
                    "item_id",
                    "description",
                    "quantity",
                    "unit_price",
                    "discount_type",
                    "discount_value",
                    "tax_code_id",
                    "revenue_account_id",
                )
                if line.get(k) not in (None, "")
            }
            for line in lines
        ],
        "notes": (data.get("notes") or "")[:2000],
        "reference": (data.get("reference") or "")[:80],
        "prices_include_tax": bool(data.get("prices_include_tax")),
        "discount_type": data.get("discount_type", "percent"),
        "discount_value": str(decimal(data.get("discount_value") or "0", "discount_value", 6)),
    }


@transaction.atomic
def save_schedule(request, data, pk=None):
    require(request.user, "invoices.create")
    schedule = Schedule.objects.select_for_update().filter(pk=pk).first() if pk else None
    if pk and schedule is None:
        raise NotFound()
    if schedule is None:
        schedule = Schedule(created_by=request.user)
    elif schedule.status in (Schedule.Status.CANCELLED, Schedule.Status.COMPLETED):
        raise BusinessRuleViolation("Cancelled or completed schedules cannot be edited.")
    for field in ("name", "frequency", "interval", "start_date", "end_date", "due_days"):
        if field in data:
            setattr(schedule, field, data[field])
    if "customer_id" in data:
        schedule.customer = Customer.objects.filter(pk=data["customer_id"], is_active=True).first()
    if schedule.customer_id is None:
        raise ValidationError({"customer_id": "Select an active customer."})
    if "project_id" in data:
        schedule.project = (
            Project.objects.filter(pk=data["project_id"]).first() if data["project_id"] else None
        )
    schedule.currency = data.get("currency") or schedule.currency or schedule.customer.currency
    enabled_currency(schedule.currency)
    if (
        pk
        and schedule.runs.exists()
        and "start_date" in data
        and data["start_date"] != schedule.start_date
    ):
        raise BusinessRuleViolation("The start date is fixed once occurrences have run.")
    if "lines" in data:
        schedule.template = _validate_template(schedule.customer, data)
    if not schedule.template.get("lines"):
        raise ValidationError({"lines": "Add at least one line to the template."})
    auto = data.get("auto_issue", schedule.auto_issue)
    if auto and not schedule.auto_issue:
        # Automatic issuance runs under the authorizing user's current permissions.
        require(request.user, "invoices.issue")
        schedule.auto_issue_authorized_by = request.user
    schedule.auto_issue = bool(auto)
    if not auto:
        schedule.auto_issue_authorized_by = None
    if pk:
        schedule.revision += 1
    schedule.full_clean()
    schedule.save()
    record(
        "billing.schedule_updated" if pk else "billing.schedule_created",
        request=request,
        target=schedule,
        after={
            "name": schedule.name,
            "frequency": schedule.frequency,
            "auto_issue": schedule.auto_issue,
        },
    )
    return schedule


@transaction.atomic
def set_status(request, pk, status):
    require(request.user, "invoices.create")
    schedule = Schedule.objects.select_for_update().filter(pk=pk).first()
    if schedule is None:
        raise NotFound()
    allowed = {
        "paused": (Schedule.Status.ACTIVE,),
        "active": (Schedule.Status.PAUSED,),
        "cancelled": (Schedule.Status.ACTIVE, Schedule.Status.PAUSED),
    }
    if schedule.status not in allowed.get(status, ()):
        raise BusinessRuleViolation(f"A {schedule.status} schedule cannot become {status}.")
    schedule.status = status
    schedule.save(update_fields=["status"])
    record(f"billing.schedule_{status}", request=request, target=schedule)
    return schedule


def preview(until):
    return [
        {"schedule": s, "dates": due_occurrences(s, until)}
        for s in Schedule.objects.filter(status=Schedule.Status.ACTIVE).select_related("customer")
    ]


def _owner(schedule, runner):
    actor = runner or schedule.created_by
    if not actor.is_active or "invoices.create" not in get_permission_codes(actor):
        raise BusinessRuleViolation("The runner can no longer create invoices.")
    return actor


def _run_one(schedule, on, actor):
    template = schedule.template
    request = common.acting(actor)
    invoice = save_invoice(
        request,
        {
            "customer_id": schedule.customer_id,
            "project_id": schedule.project_id,
            "currency": schedule.currency,
            "issue_date": on,
            "due_date": on + timedelta(days=schedule.due_days),
            "prices_include_tax": template.get("prices_include_tax", False),
            "discount_type": template.get("discount_type", "percent"),
            "discount_value": template.get("discount_value", "0"),
            "reference": template.get("reference", ""),
            "notes": template.get("notes", ""),
            "lines": template["lines"],
        },
        schedule=schedule,
    )
    status, message = Run.Status.DRAFTED, "Draft created for review."
    if schedule.auto_issue:
        issuer = schedule.auto_issue_authorized_by
        if issuer and issuer.is_active and "invoices.issue" in get_permission_codes(issuer):
            try:
                with transaction.atomic():
                    issue_invoice(common.acting(issuer), invoice.pk)
                status, message = Run.Status.ISSUED, "Issued automatically."
            except APIException as exc:
                message = f"Left as draft: {exc.detail}"[:500]
        else:
            message = "Left as draft: the authorizing user can no longer issue invoices."
    return invoice, status, message


def run_due(until=None, *, runner=None, schedule_ids=None):
    """Create invoices for every due occurrence. Returns a list of run summaries."""
    if runner is not None:
        require(runner, "invoices.create")
    until = until or timezone.localdate()
    results = []
    schedules = Schedule.objects.filter(status=Schedule.Status.ACTIVE)
    if schedule_ids:
        schedules = schedules.filter(pk__in=schedule_ids)
    for schedule_id in schedules.order_by("pk").values_list("pk", flat=True):
        with transaction.atomic():
            schedule = Schedule.objects.select_for_update().get(pk=schedule_id)
            dates = due_occurrences(schedule, until)
        for on in dates:
            results.append(_occurrence(schedule_id, on, runner))
        with transaction.atomic():
            schedule = Schedule.objects.select_for_update().get(pk=schedule_id)
            nxt = due_occurrences(schedule, date.max.replace(year=9998))
            schedule.next_run_date = nxt[0] if nxt else None
            if not nxt and schedule.end_date:
                schedule.status = Schedule.Status.COMPLETED
            schedule.save(update_fields=["next_run_date", "status"])
    return results


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
            if run and run.status != Run.Status.FAILED:
                return {
                    "schedule": schedule.pk,
                    "date": on,
                    "status": "skipped",
                    "invoice": run.invoice_id,
                }
            actor = _owner(schedule, runner)
            invoice, status, message = _run_one(schedule, on, actor)
            if run:
                run.invoice, run.status, run.message, run.run_by = invoice, status, message, actor
                run.save()
            else:
                Run.objects.create(
                    schedule=schedule,
                    occurrence_date=on,
                    invoice=invoice,
                    status=status,
                    message=message,
                    run_by=actor,
                )
        if status == Run.Status.ISSUED:
            from apps.documents.services import generate_pdf

            generate_pdf("invoice", invoice.pk)
        return {
            "schedule": schedule_id,
            "date": on,
            "status": status,
            "invoice": invoice.pk,
            "message": message,
        }
    except IntegrityError:
        # A concurrent run created this occurrence first.
        return {"schedule": schedule_id, "date": on, "status": "skipped", "invoice": None}
    except APIException as exc:
        message = str(exc.detail)[:500]
        with transaction.atomic():
            Run.objects.update_or_create(
                schedule_id=schedule_id,
                occurrence_date=on,
                defaults={"status": Run.Status.FAILED, "message": message, "invoice": None},
            )
        return {"schedule": schedule_id, "date": on, "status": "failed", "message": message}
