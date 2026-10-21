import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from django.db import DatabaseError, transaction

from apps.accounting import reports
from apps.accounting.api.views import export_csv
from apps.accounting.models import JournalEntry
from apps.accounting.services import posting
from apps.banking import services as banking
from apps.billing.services import credits, invoices
from apps.core.exceptions import BusinessRuleViolation
from apps.reporting import cash_flow
from apps.reporting.aging import aging
from apps.reporting.models import CashFlowReview

pytestmark = pytest.mark.django_db


def post_cash(books, kind, amount, on, key):
    draft = posting.save_draft(
        books.request,
        {
            "kind": kind,
            "posting_date": on,
            "description": key,
            "lines": [
                {"account_id": books.accounts["1020"].pk, "debit": amount}
                if kind == "opening"
                else {"account_id": books.accounts["6100"].pk, "debit": amount},
                {"account_id": books.accounts["3010"].pk, "credit": amount}
                if kind == "opening"
                else {"account_id": books.accounts["1020"].pk, "credit": amount},
            ],
        },
    )
    return posting.post_draft(books.request, draft.pk, key)[0]


def test_cash_flow_discloses_cutover_unclassified_and_retained_exact_review(books):
    banking.save_account(
        books.request,
        {
            "name": "Report bank",
            "kind": "bank",
            "currency": "BDT",
            "gl_account_id": books.accounts["1020"].pk,
        },
    )
    post_cash(books, "opening", "10000", date(2026, 1, 1), "report-bank-opening")
    expense = post_cash(books, "manual", "200", date(2026, 10, 1), "report-manual-expense")
    result = reports.report("cf", date(2026, 1, 1), date(2026, 10, 31))
    assert Decimal(result["opening_cutover"]) == 10000 and Decimal(result["unclassified"]) == -200
    assert Decimal(result["closing"]) == 9800 and Decimal(result["classified_difference"]) == 0
    before = JournalEntry.objects.count()
    review = cash_flow.classify(
        books.request,
        {
            "journal_id": expense.pk,
            "allocations": [
                {"category": "operating", "amount": "-190"},
                {"category": "investing", "amount": "-10"},
            ],
            "reason": "Reviewed split between operating and acquisition cost",
            "expected_version": 0,
        },
    )
    result = reports.report("cf", date(2026, 1, 1), date(2026, 10, 31))
    assert Decimal(result["operating"]) == -190 and Decimal(result["investing"]) == -10
    assert Decimal(result["unclassified"]) == Decimal(result["classified_difference"]) == 0
    assert JournalEntry.objects.count() == before
    with pytest.raises(BusinessRuleViolation):
        cash_flow.classify(
            books.request,
            {
                "journal_id": expense.pk,
                "allocations": [{"category": "operating", "amount": "-199"}],
                "reason": "Wrong allocation",
            },
        )
    with pytest.raises(DatabaseError), transaction.atomic():
        CashFlowReview.objects.filter(pk=review.pk).update(reason="Overwrite classification")


def test_aging_uses_dated_control_lines_not_current_cached_settlements(books, commerce):
    def issue(amount, on):
        doc = invoices.save_invoice(
            books.request,
            {
                "customer_id": commerce.customer.pk,
                "currency": "BDT",
                "issue_date": on,
                "due_date": on,
                "lines": [
                    {
                        "description": "Dated service",
                        "quantity": "1",
                        "unit_price": amount,
                        "revenue_account_id": books.accounts["4100"].pk,
                    }
                ],
            },
        )
        invoices.issue_invoice(books.request, doc.pk)
        return doc

    first = issue("1000", date(2026, 10, 10))
    second = issue("500", date(2026, 10, 16))
    credits.request_credit_note(
        books.request,
        first.pk,
        {
            "issue_date": date(2026, 11, 2),
            "reason": "Later service concession",
            "lines": [{"invoice_line_id": first.lines.get().pk, "amount": "200"}],
        },
        "report-november-credit",
    )
    invoices.void_invoice(books.request, second.pk, "Later dated void", date(2026, 11, 5))
    october = aging("ar", date(2026, 10, 31))
    november = aging("ar", date(2026, 11, 10))
    assert october["ledger"] == october["aged_total"] == 1500
    assert november["ledger"] == november["aged_total"] == 800
    assert october["difference"] == november["difference"] == 0


def test_dashboard_and_report_library_follow_stored_permissions(
    books, admin_client, make_user, client_for
):
    financial = admin_client.get(
        "/api/v1/reporting/dashboard/?range=custom&from=2026-01-01&to=2026-10-31"
    )
    assert financial.status_code == 200, financial.data
    assert financial.data["configured"] and financial.data["metrics"]
    assert (
        next(m for m in financial.data["metrics"] if m["key"] == "revenue")["change_percent"]
        is None
    )
    restricted = client_for(make_user("no-financial-role", None))
    data = restricted.get("/api/v1/reporting/dashboard/")
    assert data.status_code == 200 and data.data["metrics"] == [] and data.data["series"] == []
    assert restricted.get("/api/v1/reporting/reports/income/").status_code == 403
    viewer = client_for(make_user("report-viewer"))
    assert not any(r["group"] == "founder" for r in viewer.get("/api/v1/reporting/catalog/").data)
    assert viewer.post("/api/v1/reporting/cash-reviews/", {}, format="json").status_code == 403


def test_report_projection_is_paginated_and_csv_rejects_oversized_or_formula_content(
    books, admin_client
):
    response = admin_client.get(
        "/api/v1/reporting/reports/expense/?range=custom&from=2026-01-01&to=2026-10-31&page_size=1"
    )
    assert response.status_code == 200 and response.data["page_size"] == 1
    exported = export_csv(
        {"rows": [{"name": "   =1+1", "amount": "-12.34"}], "note": "@review"}, "safe-test"
    )
    parsed = list(csv.reader(io.StringIO(exported.content.decode())))
    assert parsed[1][0] == "'   =1+1" and parsed[1][1] == "'-12.34"
    assert parsed[2][1] == "'@review"
    with pytest.raises(BusinessRuleViolation):
        export_csv({"rows": [{"value": 1}] * 10001}, "too-large")


def test_recurring_run_rate_is_separate_from_unissued_drafts_and_refreshes_prices(
    books, commerce, admin_client
):
    from apps.billing.services import recurring

    plan = recurring.save_schedule(
        books.request,
        {
            "name": "Quarterly contract",
            "customer_id": commerce.customer.pk,
            "currency": "BDT",
            "frequency": "quarterly",
            "interval": 2,
            "start_date": date(2026, 1, 1),
            "lines": [
                {
                    "description": "Support",
                    "quantity": "1",
                    "unit_price": "6000",
                    "revenue_account_id": books.accounts["4100"].pk,
                    "tax_code_id": books.vat.pk,
                }
            ],
        },
    )
    recurring.run_due(date(2026, 10, 21), runner=books.request.user)
    response = admin_client.get(
        "/api/v1/reporting/reports/recurring/?from=2026-01-01&to=2026-10-31"
    )
    assert response.status_code == 200, response.data
    row = response.data["results"][0]
    assert row["id"] == plan.pk
    assert Decimal(row["run_rate"]) == 1000  # Net of tax, every two quarters.
    assert Decimal(row["actual_invoiced"]) == 0  # Draft runs are not actuals.
    assert not JournalEntry.objects.exists()


def test_report_sort_is_numeric_before_serialization_and_validates_columns(books, admin_client):
    banking.save_account(
        books.request,
        {
            "name": "Sorting bank",
            "kind": "bank",
            "currency": "BDT",
            "gl_account_id": books.accounts["1020"].pk,
        },
    )
    post_cash(books, "opening", "10000", date(2026, 1, 1), "sort-bank-opening")
    for amount in ("200", "30"):
        post_cash(books, "manual", amount, date(2026, 10, 1), "report-sort-" + amount)
    url = "/api/v1/reporting/reports/bank/?from=2026-10-01&to=2026-10-31&sort=credit"
    result = admin_client.get(url)
    assert result.status_code == 200, result.data
    assert [Decimal(row["credit"]) for row in result.data["results"]] == [30, 200]
    assert (
        admin_client.get(url + "&account_id=" + str(books.accounts["6100"].pk)).data["count"] == 0
    )
    assert admin_client.get(url + "&sort=password").status_code == 400
