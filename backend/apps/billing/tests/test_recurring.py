"""Scenario L: recurring billing runs, catch-up, idempotency and controlled issuance."""

from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounts.models import Permission
from apps.billing.models import Invoice, RecurringInvoiceRun
from apps.billing.services import recurring

from .conftest import as_user

pytestmark = pytest.mark.django_db


def schedule(commerce, **extra):
    return recurring.save_schedule(
        as_user(commerce.users.issuer),
        {
            "name": "Monthly retainer",
            "customer_id": commerce.customer.pk,
            "frequency": "monthly",
            "start_date": date(2026, 7, 31),
            "due_days": 15,
            "lines": [
                {
                    "description": "Support retainer",
                    "unit_price": "25000",
                    "tax_code_id": commerce.books.vat.pk,
                    "revenue_account_id": commerce.books.accounts["4100"].pk,
                }
            ],
            **extra,
        },
    )


def test_month_end_dates_clamp():
    assert recurring.add_period(date(2026, 1, 31), "monthly", 1, 1) == date(2026, 2, 28)
    assert recurring.add_period(date(2026, 1, 31), "quarterly", 1, 1) == date(2026, 4, 30)
    assert recurring.add_period(date(2024, 2, 29), "yearly", 1, 1) == date(2025, 2, 28)
    assert recurring.add_period(date(2026, 1, 1), "weekly", 2, 3) == date(2026, 2, 12)


def test_run_catches_up_and_is_idempotent(commerce):
    plan = schedule(commerce)
    preview = recurring.preview(date(2026, 10, 10))
    assert preview[0]["dates"] == [date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30)]
    results = recurring.run_due(date(2026, 10, 10), runner=commerce.users.issuer)
    assert [r["status"] for r in results] == ["drafted"] * 3
    drafts = Invoice.objects.filter(recurring_schedule=plan).order_by("issue_date")
    assert [d.status for d in drafts] == ["draft"] * 3 and drafts[0].due_date == date(2026, 8, 15)
    assert drafts[0].total == 27500
    # Repeating the run never duplicates; nothing is issued without review.
    assert recurring.run_due(date(2026, 10, 10), runner=commerce.users.issuer) == []
    assert (
        RecurringInvoiceRun.objects.count() == 3
        and not Invoice.objects.exclude(number=None).exists()
    )
    plan.refresh_from_db()
    assert plan.next_run_date == date(2026, 10, 31)


def test_pause_resume_cancel(commerce):
    plan = schedule(commerce)
    issuer = as_user(commerce.users.issuer)
    recurring.set_status(issuer, plan.pk, "paused")
    assert recurring.run_due(date(2026, 10, 10), runner=commerce.users.issuer) == []
    recurring.set_status(issuer, plan.pk, "active")
    assert len(recurring.run_due(date(2026, 8, 1), runner=commerce.users.issuer)) == 1
    recurring.set_status(issuer, plan.pk, "cancelled")
    assert recurring.run_due(date(2026, 12, 31), runner=commerce.users.issuer) == []


def test_auto_issue_requires_and_rechecks_issue_permission(commerce):
    plan = schedule(commerce, auto_issue=True, start_date=date(2026, 9, 30))
    assert plan.auto_issue_authorized_by == commerce.users.issuer
    results = recurring.run_due(date(2026, 9, 30), runner=commerce.users.issuer)
    assert results[0]["status"] == "issued"
    issued = Invoice.objects.get(recurring_schedule=plan)
    assert issued.number and issued.pdf_status == "ready"
    # Revoking issue rights makes later runs leave drafts instead.
    commerce.users.issuer.role.permissions.remove(Permission.objects.get(code="invoices.issue"))
    later = recurring.run_due(date(2026, 10, 31), runner=commerce.users.issuer)
    assert later[0]["status"] == "drafted" and "no longer issue" in later[0]["message"]


def test_auto_issue_cannot_be_enabled_without_issue_permission(commerce):
    from rest_framework.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        recurring.save_schedule(
            as_user(commerce.users.clerk),
            {
                "name": "x",
                "customer_id": commerce.customer.pk,
                "frequency": "monthly",
                "start_date": date(2026, 9, 1),
                "auto_issue": True,
                "lines": [
                    {
                        "description": "x",
                        "unit_price": "1",
                        "revenue_account_id": commerce.books.accounts["4100"].pk,
                    }
                ],
            },
        )


def test_management_command_uses_schedule_owner(commerce):
    schedule(commerce, start_date=date(2026, 10, 1))
    out = StringIO()
    call_command("run_recurring", "--date", "2026-10-10", stdout=out)
    assert "1 occurrences processed, 0 failed." in out.getvalue()
    call_command("run_recurring", "--date", "2026-10-10", stdout=out)
    assert Invoice.objects.count() == 1


def test_management_dry_run_lists_both_domains_without_creating_documents(commerce):
    from apps.purchasing.models import Expense
    from apps.purchasing.services import recurring as purchasing
    from apps.purchasing.services.payables import save_vendor

    invoice_schedule = schedule(commerce, start_date=date(2026, 10, 1))
    vendor = save_vendor(commerce.admin, {"name": "Renewal supplier", "currency": "BDT"})
    expense_schedule = purchasing.save_schedule(
        commerce.admin,
        {
            "name": "Renewal",
            "vendor_id": vendor.pk,
            "frequency": "monthly",
            "start_date": date(2026, 10, 1),
            "description": "Hosting",
            "amount": "100",
            "account_id": commerce.books.accounts["6100"].pk,
            "payment_mode": "accrued",
        },
    )
    out = StringIO()
    call_command("run_recurring", "--date", "2026-10-10", "--dry-run", stdout=out)
    assert f"invoice schedule {invoice_schedule.pk}: 2026-10-01" in out.getvalue()
    assert f"expense schedule {expense_schedule.pk}: 2026-10-01" in out.getvalue()
    assert not Invoice.objects.exists() and not Expense.objects.exists()
