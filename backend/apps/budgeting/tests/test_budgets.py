from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import DatabaseError, transaction
from rest_framework.exceptions import PermissionDenied

from apps.accounting.models import FiscalYear
from apps.approvals.services import decide
from apps.budgeting import services
from apps.budgeting.models import AnalyticalClassification, BudgetPublication
from apps.core.exceptions import BusinessRuleViolation
from apps.purchasing.services import payables

pytestmark = pytest.mark.django_db


def plan(books, name="Operations plan"):
    return services.create_budget(
        books.request, {"name": name, "fiscal_year_id": FiscalYear.objects.get().pk}
    )


def revision(books, budget, center=None, amount="1500", **extra):
    return services.create_revision(
        books.request,
        budget.pk,
        {
            "notes": "Reviewed operating budget",
            "lines": [
                {
                    "month": date(2026, 10, 1),
                    "account_id": books.accounts["6100"].pk,
                    "category": "operating",
                    "cost_center_id": center.pk if center else None,
                    "amount": amount,
                    **extra,
                }
            ],
        },
    )


def approve(books, obj, reviewer):
    services.submit_revision(books.request, obj.pk)
    obj.refresh_from_db()
    decide(reviewer, obj.approval_id, approve=True, reason="Independent budget review")
    obj.refresh_from_db()


def spending(books):
    vendor = payables.save_vendor(books.request, {"name": "Budget supplier", "currency": "BDT"})
    bill = payables.save_bill(
        books.request,
        {
            "vendor_id": vendor.pk,
            "vendor_reference": "BUDGET-COST-1",
            "bill_date": date(2026, 10, 1),
            "due_date": date(2026, 10, 1),
            "currency": "BDT",
            "lines": [
                {
                    "description": "Operating cost",
                    "quantity": "1",
                    "unit_price": "1000",
                    "account_id": books.accounts["6100"].pk,
                }
            ],
        },
    )
    return bill


def test_budget_actuals_use_posted_gl_and_immutable_classification_history(books, make_user):
    center = services.save_cost_center(
        books.request, {"code": "HOST", "name": "Hosting", "categories": ["operating"]}
    )
    budget = plan(books)
    rev = revision(books, budget, center)
    reviewer = SimpleNamespace(user=make_user("budget-reviewer", "administrator"), META={})
    with pytest.raises(PermissionDenied):
        submitted = services.submit_revision(books.request, rev.pk)
        decide(books.request, submitted.approval_id, approve=True)
    # The submit was retained; a denied vote has no financial or publication effect.
    rev.refresh_from_db()
    decide(reviewer, rev.approval_id, approve=True, reason="Independent budget authority")
    rev.refresh_from_db()
    bill = spending(books)
    assert Decimal(services.comparison(rev)[0]["actual"]) == 0
    payables.post_bill(books.request, bill.pk)
    bill.refresh_from_db()
    line = bill.journal.lines.get(account=books.accounts["6100"])
    tag = services.classify(
        books.request,
        {
            "line_id": line.pk,
            "cost_center_id": center.pk,
            "reason": "Hosting evidence classified to infrastructure",
        },
    )
    result = services.comparison(rev)[0]
    assert Decimal(result["actual"]) == 1000 and Decimal(result["remaining"]) == 500
    services.classify(
        books.request,
        {
            "line_id": line.pk,
            "cost_center_id": None,
            "reason": "Reviewed analytical reassignment; original journal unchanged",
        },
    )
    assert Decimal(services.comparison(rev)[0]["actual"]) == 0
    assert AnalyticalClassification.objects.filter(line=line).count() == 2
    line.refresh_from_db()
    assert line.base_debit == 1000 and line.dimensions.get("cost_center") is None
    with pytest.raises(DatabaseError), transaction.atomic():
        AnalyticalClassification.objects.filter(pk=tag.pk).update(reason="Overwrite evidence")


def test_budget_versions_preserve_original_and_revised_approvals(books, make_user):
    budget = plan(books)
    reviewer = SimpleNamespace(user=make_user("budget-approver", "administrator"), META={})
    original = revision(books, budget)
    approve(books, original, reviewer)
    updated = revision(books, budget, amount="2500")
    approve(books, updated, reviewer)
    budget.refresh_from_db()
    assert budget.original_revision_id == original.pk and budget.active_revision_id == updated.pk
    assert BudgetPublication.objects.filter(budget=budget).count() == 2
    result = services.comparison(updated)[0]
    assert Decimal(result["original"]) == 1500 and Decimal(result["revised"]) == 2500
    with pytest.raises(DatabaseError), transaction.atomic():
        updated.lines.update(amount="1")


def test_overlapping_budget_scopes_are_rejected_at_independent_publication(books, make_user):
    reviewer = SimpleNamespace(user=make_user("scope-reviewer", "administrator"), META={})
    first = revision(books, plan(books, "Global operating plan"))
    approve(books, first, reviewer)
    center = services.save_cost_center(books.request, {"code": "ADMIN", "name": "Administration"})
    other = revision(books, plan(books, "Overlapping plan"), center)
    services.submit_revision(books.request, other.pk)
    other.refresh_from_db()
    with pytest.raises(BusinessRuleViolation):
        decide(reviewer, other.approval_id, approve=True)
    assert BudgetPublication.objects.count() == 1


def test_annual_budget_allocates_exact_minor_units_and_restricts_direct_api(
    books, make_user, client_for
):
    obj = revision(books, plan(books), amount="100.01", annual=True)
    assert obj.lines.count() == 12
    assert sum((line.amount for line in obj.lines.all()), Decimal(0)) == Decimal("100.01")
    viewer = client_for(make_user("budget-viewer"))
    assert viewer.get("/api/v1/budgeting/budgets/").status_code == 200
    assert (
        viewer.post(
            "/api/v1/budgeting/cost-centers/", {"code": "NO", "name": "Denied"}, format="json"
        ).status_code
        == 403
    )
