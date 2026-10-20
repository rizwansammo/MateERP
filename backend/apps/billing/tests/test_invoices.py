"""Scenarios B, G, R, S, T: issuance, duplicates, period locks, approvals, branding history."""

import io
from datetime import date
from decimal import Decimal as D

import pytest
from django.db import IntegrityError, transaction
from pypdf import PdfReader
from rest_framework.exceptions import APIException, PermissionDenied

from apps.accounting.models import AccountingPeriod, JournalEntry
from apps.accounting.services import posting
from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.billing.models import Invoice
from apps.billing.services import invoices
from apps.branding.models import BrandingVersion
from apps.branding.services import publish, save_draft
from apps.documents.models import FiledDocument
from apps.documents.services import generate_pdf
from apps.files.services import private_storage
from apps.sales import services as sales

from .conftest import DAY, as_user, draft, issued

pytestmark = pytest.mark.django_db


def lines_of(journal):
    return [
        (line.account.code, line.debit, line.credit, line.base_debit, line.base_credit)
        for line in journal.lines.select_related("account")
    ]


def test_issue_posts_receivable_and_freezes_snapshot(commerce):
    invoice = issued(commerce)
    assert invoice.number == "INV-2026-0001" and invoice.status == "issued"
    assert lines_of(invoice.journal) == [
        ("1100", D("11000"), 0, D("11000"), 0),
        ("4100", 0, D("10000"), 0, D("10000")),
        ("2100", 0, D("1000"), 0, D("1000")),
    ]
    assert (
        invoice.journal.source_type == "invoice"
        and invoice.journal.posted_by == commerce.users.issuer
    )
    assert invoice.branding_version == BrandingVersion.objects.get()
    assert invoice.snapshot["totals"]["total"] == "11000.00"
    assert invoice.snapshot["customer"]["name"] == "Acme Trading Ltd"
    assert invoice.snapshot["company"]["display_name"] == "NetaMate"
    # Retrying issue returns the same invoice and posts nothing more.
    again = invoices.issue_invoice(as_user(commerce.users.issuer), invoice.pk)
    assert again.journal_id == invoice.journal_id and JournalEntry.objects.count() == 1


def test_official_pdf_is_generated_filed_and_immutable(commerce):
    invoice = issued(commerce)
    invoice = generate_pdf("invoice", invoice.pk)
    assert invoice.pdf_status == "ready"
    with private_storage().open(invoice.pdf_file.storage_name, "rb") as fh:
        # pypdf interleaves NULs when decoding WeasyPrint's two-byte CMaps; normalise.
        text = PdfReader(io.BytesIO(fh.read())).pages[0].extract_text().replace("\x00", "")
    assert "INV-2026-0001" in text and "11,000.00" in text and "Acme Trading Ltd" in text
    filed = FiledDocument.objects.get(invoice=invoice)
    assert filed.generated and filed.kind == "invoice" and filed.customer == commerce.customer
    # Generating again never replaces the official file.
    assert generate_pdf("invoice", invoice.pk).pdf_file_id == invoice.pdf_file_id
    with pytest.raises(IntegrityError), transaction.atomic():
        Invoice.objects.filter(pk=invoice.pk).update(pdf_file=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        FiledDocument.objects.filter(pk=filed.pk).delete()


def test_pdf_failure_is_retryable_without_partial_issue(commerce, monkeypatch):
    from apps.documents import services as documents

    invoice = issued(commerce)

    def broken(*args, **kwargs):
        raise RuntimeError("renderer down")

    monkeypatch.setattr(documents, "_render", broken)
    failed = generate_pdf("invoice", invoice.pk)
    assert failed.pdf_status == "failed" and failed.number == "INV-2026-0001"
    assert failed.journal_id and not FiledDocument.objects.exists()
    monkeypatch.undo()
    assert generate_pdf("invoice", invoice.pk).pdf_status == "ready"


def test_issued_content_is_immutable_at_database_level(commerce):
    invoice = issued(commerce)
    for change in ({"total": D("1")}, {"number": "X-1"}, {"snapshot": {}}):
        with pytest.raises(IntegrityError), transaction.atomic():
            Invoice.objects.filter(pk=invoice.pk).update(**change)
    with pytest.raises(IntegrityError), transaction.atomic():
        invoice.lines.update(unit_price=D("1"))
    with pytest.raises(APIException):
        invoices.save_invoice(
            as_user(commerce.users.issuer), {"revision": invoice.revision, "notes": "x"}, invoice.pk
        )


def test_issue_requires_domain_permission_not_accounting(commerce):
    invoice = draft(commerce, user=commerce.users.clerk)
    with pytest.raises(PermissionDenied):
        invoices.issue_invoice(as_user(commerce.users.clerk), invoice.pk)
    with pytest.raises(PermissionDenied):
        invoices.issue_invoice(as_user(commerce.users.viewer), invoice.pk)
    # The issuer posts a journal although they do not hold accounting.manage…
    issued_invoice = invoices.issue_invoice(as_user(commerce.users.issuer), invoice.pk)
    assert issued_invoice.journal.status == "posted"
    # …and cannot reverse it through the public accounting path.
    with pytest.raises(PermissionDenied):
        posting.reverse(
            as_user(commerce.users.issuer), issued_invoice.journal_id, DAY, "x", "public-key-1"
        )
    with pytest.raises(APIException) as owned:
        posting.reverse(commerce.admin, issued_invoice.journal_id, DAY, "x", "public-key-2")
    assert owned.value.get_codes() == "domain_owned"


def test_setup_errors_are_actionable(commerce):
    from apps.accounting.models import Account

    invoice = draft(commerce)
    Account.objects.filter(control="receivable").update(control="")
    with pytest.raises(APIException) as missing:
        invoices.issue_invoice(as_user(commerce.users.issuer), invoice.pk)
    assert missing.value.get_codes() == "receivable_control_required"
    assert "Chart of accounts" in str(missing.value.detail)


def test_issue_without_published_branding_is_refused(books, user_with):
    from apps.billing.services.invoices import issue_invoice, save_invoice
    from apps.billing.tests.conftest import as_user as act

    customer = sales.save_customer(books.request, {"name": "No Brand Co", "currency": "BDT"})
    issuer = user_with("issuer2", "finance.view", "invoices.create", "invoices.issue")
    invoice = save_invoice(
        act(issuer),
        {
            "customer_id": customer.pk,
            "issue_date": DAY,
            "lines": [
                {
                    "description": "x",
                    "unit_price": "10",
                    "revenue_account_id": books.accounts["4100"].pk,
                }
            ],
        },
    )
    with pytest.raises(APIException) as refused:
        issue_invoice(act(issuer), invoice.pk)
    assert refused.value.get_codes() == "branding_required"
    invoice.refresh_from_db()
    assert invoice.number is None and not JournalEntry.objects.exists()


def test_closed_period_blocks_issue_atomically(commerce):
    invoice = draft(commerce)
    AccountingPeriod.objects.filter(start=date(2026, 10, 1)).update(is_closed=True)
    with pytest.raises(APIException):
        invoices.issue_invoice(as_user(commerce.users.issuer), invoice.pk)
    invoice.refresh_from_db()
    assert invoice.number is None and invoice.status in ("draft", "approved")
    assert not JournalEntry.objects.exists()


def test_numbers_are_sequential_and_never_reused(commerce):
    first = issued(commerce)
    second = issued(commerce)
    invoices.void_invoice(as_user(commerce.users.issuer), first.pk, "Raised in error")
    third = issued(commerce)
    assert [first.number, second.number, third.number] == [
        "INV-2026-0001",
        "INV-2026-0002",
        "INV-2026-0003",
    ]


def test_void_reverses_exactly_and_frees_nothing_twice(commerce):
    invoice = issued(commerce)
    void = invoices.void_invoice(as_user(commerce.users.issuer), invoice.pk, "Duplicate billing")
    assert void.status == "void" and void.void_journal.reversal_of_id == invoice.journal_id
    assert sorted(lines_of(void.void_journal)) == sorted(
        (c, cr, dr, bcr, bdr) for c, dr, cr, bdr, bcr in lines_of(invoice.journal)
    )
    with pytest.raises(APIException):
        invoices.void_invoice(as_user(commerce.users.issuer), invoice.pk, "")


def test_milestone_and_order_cannot_be_invoiced_twice(commerce):
    admin = commerce.admin
    project = sales.save_project(
        admin,
        {
            "reference": "PRJ-1",
            "name": "Rollout",
            "customer_id": commerce.customer.pk,
            "currency": "BDT",
            "contract_value": "100000",
            "milestones": [{"name": "Start", "percent": "40"}, {"name": "End", "percent": "60"}],
        },
    )
    milestone = project.milestones.first()
    issuer = as_user(commerce.users.issuer)
    first = invoices.create_from_milestone(
        issuer,
        milestone.pk,
        {"issue_date": DAY, "revenue_account_id": commerce.books.accounts["4100"].pk},
    )
    assert first.total == D("40000")
    with pytest.raises(APIException) as twice:
        invoices.create_from_milestone(
            issuer,
            milestone.pk,
            {"issue_date": DAY, "revenue_account_id": commerce.books.accounts["4100"].pk},
        )
    assert twice.value.get_codes() == "milestone_invoiced"
    with pytest.raises(IntegrityError), transaction.atomic():
        Invoice.objects.create(
            customer=commerce.customer,
            milestone=milestone,
            issue_date=DAY,
            due_date=DAY,
            currency="BDT",
            created_by=commerce.users.issuer,
        )
    order = sales.save_order(
        admin,
        {
            "customer_id": commerce.customer.pk,
            "order_date": DAY,
            "lines": [{"description": "Licences", "quantity": "10", "unit_price": "100"}],
        },
    )
    sales.confirm_order(admin, order.pk)
    from apps.billing.models import LedgerSettings

    LedgerSettings.objects.update_or_create(
        pk=1, defaults={"default_revenue_account": commerce.books.accounts["4100"]}
    )
    partial = invoices.save_invoice(
        issuer,
        {
            "customer_id": commerce.customer.pk,
            "sales_order_id": order.pk,
            "issue_date": DAY,
            "lines": [
                {
                    "sales_order_line_id": order.lines.get().pk,
                    "description": "Licences",
                    "quantity": "4",
                    "unit_price": "100",
                }
            ],
        },
    )
    invoices.issue_invoice(issuer, partial.pk)
    order.refresh_from_db()
    assert order.status == "partially_invoiced"
    rest = invoices.create_from_order(issuer, order.pk, {"issue_date": DAY})
    assert rest.lines.get().quantity == D("6")
    with pytest.raises(APIException):
        invoices.create_from_order(issuer, order.pk, {"issue_date": DAY})
    invoices.issue_invoice(issuer, rest.pk)
    order.refresh_from_db()
    assert order.status == "invoiced"


def test_invoice_approval_policy_and_segregation(commerce, user_with):
    policy = ApprovalPolicy.objects.get(category="invoices")
    policy.is_required = True
    policy.amount_threshold = D("5000")
    policy.save()
    issuer = as_user(commerce.users.issuer)
    small = draft(
        commerce,
        lines=[
            {
                "description": "Small",
                "unit_price": "100",
                "revenue_account_id": commerce.books.accounts["4100"].pk,
            }
        ],
    )
    assert invoices.issue_invoice(issuer, small.pk).status == "issued"
    big = draft(commerce)
    with pytest.raises(APIException) as needs:
        invoices.issue_invoice(issuer, big.pk)
    assert needs.value.get_codes() == "approval_required"
    pending = invoices.approve_invoice(issuer, big.pk)
    assert pending.status == "pending_approval"
    with pytest.raises(PermissionDenied):
        decide(issuer, pending.approval_id, approve=True)
    approver = user_with("approver", "finance.view", "invoices.issue")
    policy.approver_role = approver.role
    policy.save()
    decide(as_user(approver), pending.approval_id, approve=True)
    pending.refresh_from_db()
    assert pending.status == "approved" and pending.approved_by == approver
    assert invoices.issue_invoice(issuer, big.pk).number


def test_rejected_approval_returns_invoice_to_draft(commerce, user_with):
    policy = ApprovalPolicy.objects.get(category="invoices")
    policy.is_required = True
    approver = user_with("approver", "finance.view", "invoices.issue")
    policy.approver_role = approver.role
    policy.save()
    invoice = invoices.approve_invoice(as_user(commerce.users.issuer), draft(commerce).pk)
    decide(as_user(approver), invoice.approval_id, approve=False, reason="Wrong rate")
    invoice.refresh_from_db()
    assert invoices.sync_approval(invoice).status == "draft"


def test_issued_invoice_keeps_its_branding_version(commerce):
    first = issued(commerce)
    save_draft(
        commerce.admin,
        {**first.branding_version.config, "invoice_template": "atlas", "brand_color": "#123456"},
    )
    publish(commerce.admin, label="New look")
    second = issued(commerce)
    assert first.branding_version.number == 1 and second.branding_version.number == 2
    first.refresh_from_db()
    assert first.branding_version.config["invoice_template"] == "meridian"
    assert generate_pdf("invoice", first.pk).pdf_status == "ready"
    assert generate_pdf("invoice", second.pk).pdf_status == "ready"
