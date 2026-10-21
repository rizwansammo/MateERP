from datetime import date
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.accounting.models import JournalEntry
from apps.accounting.services import onboarding
from apps.approvals.services import decide
from apps.banking import services as banking
from apps.core.exceptions import BusinessRuleViolation
from apps.purchasing.models import Expense
from apps.purchasing.services import payables


def test_linked_historical_obligation_reuses_posted_source_without_second_journal(books, make_user):
    from apps.purchasing.services.payables import post_bill, save_bill, save_vendor

    vendor = save_vendor(books.request, {"name": "Historical supplier", "currency": "BDT"})
    bill = save_bill(
        books.request,
        {
            "vendor_id": vendor.pk,
            "vendor_reference": "LINKED-HISTORY-1",
            "bill_date": date(2026, 10, 1),
            "due_date": date(2026, 10, 1),
            "currency": "BDT",
            "lines": [
                {
                    "description": "Documented old obligation",
                    "quantity": "1",
                    "unit_price": "1000",
                    "account_id": books.accounts["6100"].pk,
                }
            ],
        },
    )
    post_bill(books.request, bill.pk)
    bill.refresh_from_db()
    source = historical(books, "vendor_payable", reference="LINKED-HISTORY-1")
    treatment = onboarding.request_treatment(
        books.request,
        source.pk,
        {
            "mode": "linked",
            "recognition_date": date(2026, 10, 1),
            "reason": (
                "Independent review of original January evidence and permitted October recognition"
            ),
            "payload": {
                "source_id": bill.pk,
                "corporate_adoption_reference": "APPROVED-ADOPTION-01",
            },
        },
    )
    before = JournalEntry.objects.count()
    decide(
        independent(make_user),
        treatment.approval_id,
        approve=True,
        reason="Verified source and corporate adoption match",
    )
    treatment.refresh_from_db()
    assert treatment.vendor_bill_id == bill.pk and treatment.journal_id == bill.journal_id
    assert JournalEntry.objects.count() == before
    assert source.original_date == date(2026, 1, 5)


pytestmark = pytest.mark.django_db


def historical(books, classification="company_expense", reference="HIST-2026-001", **extra):
    return onboarding.document(
        books.request,
        {
            "external_reference": reference,
            "original_date": date(2026, 1, 5),
            "description": "Historical startup hosting",
            "currency": "BDT",
            "amount": "1000.00",
            "payment_source": "Documented original source",
            "funding_classification": classification,
            "pre_registration": True,
            **extra,
        },
    )


def independent(make_user):
    return SimpleNamespace(user=make_user("reviewer", "administrator"), META={})


def test_pre_registration_evidence_has_no_company_obligation(books, admin_client):
    obj = historical(books)
    assert obj.pre_registration
    assert not JournalEntry.objects.exists()
    assert not Expense.objects.exists()
    assert admin_client.get(f"/api/v1/accounting/historical-records/{obj.pk}/").status_code == 200


def test_historical_adoption_prepares_existing_expense_and_preserves_both_dates(books, make_user):
    source = historical(books)
    bank = banking.save_account(
        books.request,
        {
            "name": "Operating bank",
            "kind": "bank",
            "currency": "BDT",
            "gl_account_id": books.accounts["1020"].pk,
        },
    )
    treatment = onboarding.request_treatment(
        books.request,
        source.pk,
        {
            "mode": "reconstructed",
            "recognition_date": date(2026, 10, 1),
            "reason": "Documented corporate adoption; January period closed; "
            "recognition reviewed for October",
            "payload": {
                "payment_mode": "paid",
                "bank_account_id": bank.pk,
                "account_id": books.accounts["6100"].pk,
            },
        },
    )
    with pytest.raises(PermissionDenied):
        decide(books.request, treatment.approval_id, approve=True, reason="Self approval denied")
    reviewer = independent(make_user)
    decide(
        reviewer,
        treatment.approval_id,
        approve=True,
        reason="Evidence and recognition basis checked",
    )
    treatment.refresh_from_db()
    expense = treatment.expense
    assert expense.original_transaction_date == date(2026, 1, 5)
    assert expense.expense_date == date(2026, 10, 1)
    assert expense.status == "draft" and not JournalEntry.objects.exists()
    payables.post_expense(reviewer, expense.pk)
    expense.refresh_from_db()
    assert expense.journal.posting_date == date(2026, 10, 1)
    with pytest.raises(BusinessRuleViolation):
        onboarding.request_treatment(
            books.request,
            source.pk,
            {
                "mode": "opening_only",
                "recognition_date": date(2026, 10, 1),
                "reason": "Must not repeat",
            },
        )


def test_opening_bank_does_not_repeat_historical_expenses(books, make_user):
    bank = banking.save_account(
        books.request,
        {
            "name": "Cutover bank",
            "kind": "bank",
            "currency": "BDT",
            "gl_account_id": books.accounts["1020"].pk,
        },
    )
    source = historical(books, "bank_balance", pre_registration=False)
    treatment = onboarding.request_treatment(
        books.request,
        source.pk,
        {
            "mode": "opening_only",
            "recognition_date": date(2026, 10, 1),
            "reason": "Verified prior bank statement",
            "payload": {"bank_id": bank.pk, "opening_equity_account_id": books.accounts["3010"].pk},
        },
    )
    decide(
        independent(make_user),
        treatment.approval_id,
        approve=True,
        reason="Opening statement checked",
    )
    treatment.refresh_from_db()
    assert treatment.journal.lines.get(account=bank.gl_account).debit == 1000
    assert not treatment.journal.lines.filter(account__account_type="expense").exists()
    assert not Expense.objects.exists()
    with pytest.raises(BusinessRuleViolation):
        onboarding.request_treatment(
            books.request,
            source.pk,
            {
                "mode": "reconstructed",
                "recognition_date": date(2026, 10, 1),
                "reason": "Duplicate prohibited",
            },
        )


def test_original_date_restriction_and_permission(books, user_with, client_for):
    user = user_with("ordinary_expense", "finance.view", "expenses.manage")
    response = client_for(user).post(
        "/api/v1/purchasing/expenses/",
        {
            "expense_date": "2026-10-01",
            "original_transaction_date": "2026-01-05",
            "recognition_reason": "Reviewed historical entry",
            "description": "Historical service",
            "currency": "BDT",
            "payment_mode": "accrued",
            "amount": "1000.00",
            "account_id": books.accounts["6100"].pk,
        },
        format="json",
    )
    assert response.status_code == 403


def test_opening_vendor_obligation_reconciles_without_a_historical_expense(books, make_user):
    from apps.purchasing.services.reconciliation import payables as reconcile_payables

    vendor = payables.save_vendor(books.request, {"name": "Prior supplier", "currency": "BDT"})
    source = historical(books, "vendor_payable", pre_registration=False)
    treatment = onboarding.request_treatment(
        books.request,
        source.pk,
        {
            "mode": "opening_only",
            "recognition_date": date(2026, 10, 1),
            "reason": "Prior supplier statement reviewed",
            "payload": {
                "vendor_id": vendor.pk,
                "opening_equity_account_id": books.accounts["3010"].pk,
            },
        },
    )
    decide(
        independent(make_user),
        treatment.approval_id,
        approve=True,
        reason="Supplier opening verified",
    )
    treatment.refresh_from_db()
    assert treatment.vendor_bill.outstanding == 1000
    assert not treatment.journal.lines.filter(account__account_type="expense").exists()
    assert reconcile_payables()["difference"] == 0


def test_rejected_treatment_keeps_evidence_and_allows_corrected_review(books, make_user):
    source = historical(books)
    first = onboarding.request_treatment(
        books.request,
        source.pk,
        {
            "mode": "reconstructed",
            "recognition_date": date(2026, 10, 1),
            "reason": "Incorrect proposed original bank funding; independent reviewer rejects it",
        },
    )
    decide(independent(make_user), first.approval_id, approve=False, reason="Use reconstruction")
    second = onboarding.request_treatment(
        books.request,
        source.pk,
        {
            "mode": "reconstructed",
            "recognition_date": date(2026, 10, 1),
            "reason": "Corrected source treatment",
        },
    )
    assert second.pk != first.pk and source.treatments.count() == 2
    assert not JournalEntry.objects.exists()


def test_personal_historical_evidence_is_hidden_in_metadata_reports_and_file_bytes(
    books, user_with, client_for
):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from apps.company.models import FinancialParty

    participant = user_with(
        "history-participant",
        "onboarding.manage",
        "finance.view",
        "founder.view",
        "founder.personal.view",
    )
    party = FinancialParty.objects.create(
        name="Documented personal participant",
        kind="individual",
        joined=date(2026, 1, 1),
        user=participant,
    )
    image = BytesIO()
    Image.new("RGB", (2, 2), (0, 176, 240)).save(image, format="PNG")
    data = {
        "external_reference": "PERSONAL-HISTORY-PRIVATE",
        "original_date": date(2026, 1, 5),
        "description": "Authorized personal provenance",
        "currency": "BDT",
        "amount": "1000",
        "payment_source": "Personal transfer evidence",
        "funding_classification": "personal_settlement",
        "pre_registration": True,
        "party_id": party.pk,
    }
    obj = onboarding.document(
        books.request,
        data,
        SimpleUploadedFile("personal.png", image.getvalue(), content_type="image/png"),
    )
    for name, codes in (
        ("no-personal-history", ["onboarding.manage", "finance.view", "founder.view"]),
        (
            "unrelated-personal-reviewer",
            ["onboarding.manage", "finance.view", "founder.view", "founder.personal.view"],
        ),
    ):
        client = client_for(user_with(name, *codes))
        assert client.get(f"/api/v1/accounting/historical-records/{obj.pk}/").status_code == 404
        assert client.get(f"/api/v1/files/{obj.evidence_id}/content/").status_code == 404
        report = client.get("/api/v1/reporting/reports/history/?from=2026-01-01&to=2026-12-31")
        assert report.status_code == 200 and report.data["count"] == 0
    allowed = client_for(participant)
    assert allowed.get(f"/api/v1/accounting/historical-records/{obj.pk}/").status_code == 200
    content = allowed.get(f"/api/v1/files/{obj.evidence_id}/content/")
    assert content.status_code == 200 and content["Cache-Control"] == "private, no-store"
    content.close()
