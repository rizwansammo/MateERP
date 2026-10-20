"""Scenarios D, E, F, H, Q, R: payments, verification, receipts, credits, refunds, FX, GL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal as D
from threading import Barrier

import pytest
from django.db import close_old_connections, connection
from rest_framework.exceptions import APIException, PermissionDenied

from apps.accounting.models import JournalLine
from apps.accounting.services import setup
from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.banking import services as banking
from apps.billing.models import CustomerPayment, Invoice, MoneyReceipt
from apps.billing.services import credits, payments, reconciliation
from apps.company.services import update_business_settings
from apps.documents.services import generate_pdf
from apps.sales.services import save_customer

from .conftest import DAY, as_user, issued

pytestmark = pytest.mark.django_db


def line(commerce, price="100000", tax=False):
    row = {
        "description": "Retainer",
        "quantity": "1",
        "unit_price": price,
        "revenue_account_id": commerce.books.accounts["4100"].pk,
    }
    if tax:
        row["tax_code_id"] = commerce.books.vat.pk
    return [row]


def record(commerce, invoice, amount, key, *, total=None, **extra):
    return payments.record_payment(
        as_user(commerce.users.recorder),
        {
            "customer_id": invoice.customer_id,
            "bank_account_id": extra.pop("bank", commerce.bank).pk,
            "payment_date": extra.pop("on", DAY),
            "amount": total or amount,
            "allocations": [{"invoice_id": invoice.pk, "amount": amount}] if amount else [],
            **extra,
        },
        key,
    )


def verify(commerce, payment):
    return payments.verify_payment(as_user(commerce.users.verifier), payment.pk)


def assert_reconciled():
    result = reconciliation.receivables()
    assert result["receivable"]["difference"] == 0, result
    assert result["customer_credit"]["difference"] == 0, result
    return result


def test_partial_payments_settle_exactly(commerce):
    invoice = issued(commerce, lines=line(commerce))
    for i, amount in enumerate(("30000", "50000", "20000")):
        verify(commerce, record(commerce, invoice, amount, f"partial-payment-{i}"))
        invoice.refresh_from_db()
        assert invoice.status == ("paid" if i == 2 else "partially_paid")
    assert invoice.outstanding == 0 and invoice.base_settled == invoice.base_total
    assert assert_reconciled()["receivable"]["ledger"] == 0
    assert MoneyReceipt.objects.count() == 3
    numbers = list(MoneyReceipt.objects.order_by("pk").values_list("number", flat=True))
    assert numbers == ["MR-2026-0001", "MR-2026-0002", "MR-2026-0003"]


def test_recording_has_no_ledger_effect_and_verification_posts(commerce):
    invoice = issued(commerce, lines=line(commerce, tax=True))
    payment = record(commerce, invoice, "11000", "verify-posts-1")
    assert payment.status == "pending_verification" and payment.journal is None
    assert not MoneyReceipt.objects.exists()
    invoice.refresh_from_db()
    assert invoice.amount_paid == 0
    payment = verify(commerce, payment)
    lines = [
        (ln.account.code, ln.debit, ln.credit)
        for ln in payment.journal.lines.select_related("account")
    ]
    assert lines == [("1020", D("11000"), 0), ("1100", 0, D("11000"))]
    assert payment.receipt.number == "MR-2026-0001"
    receipt = generate_pdf("receipt", payment.receipt.pk)
    assert (
        receipt.pdf_status == "ready" and receipt.branding_version_id == invoice.branding_version_id
    )


def test_verification_is_segregated_and_permissioned(commerce, user_with):
    invoice = issued(commerce, lines=line(commerce))
    payment = record(commerce, invoice, "100000", "segregation-1")
    with pytest.raises(PermissionDenied):
        payments.verify_payment(as_user(commerce.users.viewer), payment.pk)
    both = user_with("both", "finance.view", "payments.record", "payments.approve")
    other = issued(commerce, lines=line(commerce, "10"))
    own = payments.record_payment(
        as_user(both),
        {
            "customer_id": other.customer_id,
            "bank_account_id": commerce.bank.pk,
            "payment_date": DAY,
            "amount": "1",
            "allocations": [{"invoice_id": other.pk, "amount": "1"}],
        },
        "own-payment-1",
    )
    with pytest.raises(PermissionDenied):
        payments.verify_payment(as_user(both), own.pk)
    with pytest.raises(PermissionDenied):
        payments.reject_payment(as_user(both), own.pk, "self")
    assert verify(commerce, payment).status == "verified"
    with pytest.raises(PermissionDenied):
        payments.record_payment(as_user(commerce.users.verifier), {}, "verifier-cannot-record")


def test_idempotent_recording_and_conflicts(commerce):
    invoice = issued(commerce, lines=line(commerce))
    first = record(commerce, invoice, "1000", "same-key-123")
    assert record(commerce, invoice, "1000", "same-key-123").pk == first.pk
    with pytest.raises(APIException) as conflict:
        record(commerce, invoice, "2000", "same-key-123")
    assert conflict.value.get_codes() == "idempotency_conflict"
    assert CustomerPayment.objects.count() == 1
    verified = verify(commerce, first)
    # Verifying again is a no-op that returns the same posting.
    assert verify(commerce, first).journal_id == verified.journal_id


def test_overallocation_is_blocked(commerce):
    invoice = issued(commerce, lines=line(commerce))
    record(commerce, invoice, "60000", "pending-1")
    with pytest.raises(APIException) as reserved:
        record(commerce, invoice, "50000", "pending-2")
    assert reserved.value.get_codes() == "overallocation"
    with pytest.raises(APIException):
        record(commerce, invoice, "100001", "too-much-1")


@pytest.mark.django_db(transaction=True)
def test_concurrent_verifications_cannot_overallocate(commerce):
    invoice = issued(commerce, lines=line(commerce))
    first = record(commerce, invoice, "60000", "race-key-1")
    # Bypass the recording-time reservation to force a verification race.
    second = record(commerce, invoice, "40000", "race-key-2")
    CustomerPayment.objects.filter(pk=first.pk).update(amount=D("70000"))
    first.allocations.update(amount=D("70000"))
    barrier = Barrier(2)

    def attempt(pk):
        close_old_connections()
        barrier.wait()
        try:
            payments.verify_payment(as_user(commerce.users.verifier), pk)
            return "ok"
        except APIException as exc:
            return exc.get_codes()
        finally:
            connection.close()

    with ThreadPoolExecutor(2) as pool:
        results = sorted(pool.map(attempt, [first.pk, second.pk]))
    invoice.refresh_from_db()
    assert results.count("ok") == 1 and invoice.amount_paid <= invoice.total
    assert assert_reconciled()


def test_unapplied_credit_application_and_refund(commerce):
    invoice = issued(commerce, lines=line(commerce, "1000"))
    payment = record(commerce, invoice, "1000", "overpay-1", total="1500", accept_unapplied=True)
    payment = verify(commerce, payment)
    assert payment.unapplied_amount == D("500")
    assert credits.credit_balance(commerce.customer.pk, "BDT") == (D("500"), D("500"))
    second = issued(commerce, lines=line(commerce, "300"))
    credits.apply_credit(
        as_user(commerce.users.recorder),
        {"invoice_id": second.pk, "amount": "300"},
        "apply-credit-1",
    )
    second.refresh_from_db()
    assert second.status == "paid"
    with pytest.raises(APIException):
        credits.request_refund(
            as_user(commerce.users.crediter),
            {
                "customer_id": commerce.customer.pk,
                "bank_account_id": commerce.bank.pk,
                "amount": "201",
                "reason": "Too much",
            },
            "refund-too-much",
        )
    refund = credits.request_refund(
        as_user(commerce.users.crediter),
        {
            "customer_id": commerce.customer.pk,
            "bank_account_id": commerce.bank.pk,
            "amount": "200",
            "reason": "Return balance",
        },
        "refund-ok-1",
    )
    assert refund.status == "paid"
    assert [
        (ln.account.code, ln.debit, ln.credit)
        for ln in refund.journal.lines.select_related("account")
    ] == [
        ("2200", D("200"), 0),
        ("1020", 0, D("200")),
    ]
    assert credits.credit_balance(commerce.customer.pk, "BDT")[0] == 0
    assert_reconciled()


def test_credit_notes_reverse_tax_and_respect_limits(commerce):
    invoice = issued(commerce, lines=line(commerce, "10000", tax=True))
    crediter = as_user(commerce.users.crediter)
    partial = credits.request_credit_note(
        crediter,
        invoice.pk,
        {
            "reason": "Scope reduced",
            "lines": [{"invoice_line_id": invoice.lines.get().pk, "amount": "2200"}],
        },
        "credit-1",
    )
    assert (partial.taxable, partial.tax, partial.total) == (D("2000"), D("200"), D("2200"))
    lines = sorted(
        (ln.account.code, ln.debit, ln.credit)
        for ln in partial.journal.lines.select_related("account")
    )
    assert lines == [("1100", 0, D("2200")), ("2100", D("200"), 0), ("4100", D("2000"), 0)]
    with pytest.raises(APIException) as over:
        credits.request_credit_note(
            crediter,
            invoice.pk,
            {
                "reason": "Too much",
                "lines": [{"invoice_line_id": invoice.lines.get().pk, "amount": "8801"}],
            },
            "credit-2",
        )
    assert over.value.get_codes() == "overcredit"
    verify(commerce, record(commerce, invoice, "8800", "pay-rest-1"))
    # Crediting a paid invoice moves the excess to customer credit, never negative AR.
    full = credits.request_credit_note(
        crediter, invoice.pk, {"reason": "Cancelled", "full": True}, "credit-3"
    )
    assert full.applied_amount == 0 and full.credit_amount == D("8800")
    invoice.refresh_from_db()
    assert invoice.status == "paid" and invoice.outstanding == 0
    assert credits.credit_balance(commerce.customer.pk, "BDT")[0] == D("8800")
    assert generate_pdf("credit_note", full.pk).pdf_status == "ready"
    with pytest.raises(PermissionDenied):
        credits.request_credit_note(
            as_user(commerce.users.recorder), invoice.pk, {"reason": "x", "full": True}, "credit-4"
        )
    assert_reconciled()


def test_payment_reversal_reopens_invoice_and_cancels_receipt(commerce):
    invoice = issued(commerce, lines=line(commerce))
    payment = verify(commerce, record(commerce, invoice, "100000", "reverse-1"))
    reversed_ = payments.reverse_payment(
        as_user(commerce.users.verifier), payment.pk, "Cheque bounced"
    )
    invoice.refresh_from_db()
    assert (
        reversed_.status == "reversed"
        and invoice.status == "issued"
        and invoice.outstanding == D("100000")
    )
    assert MoneyReceipt.objects.get().status == "cancelled"
    assert_reconciled()


def test_approval_threshold_routes_verification(commerce, user_with):
    policy = ApprovalPolicy.objects.get(category="client_payments")
    policy.is_required = True
    policy.amount_threshold = D("50000")
    approver = user_with("approver", "finance.view", "payments.approve")
    policy.approver_role = approver.role
    policy.save()
    invoice = issued(commerce, lines=line(commerce))
    payment = verify(commerce, record(commerce, invoice, "60000", "threshold-1"))
    assert payment.status == "awaiting_approval" and payment.journal is None
    decide(as_user(approver), payment.approval_id, approve=True)
    payment.refresh_from_db()
    assert payment.status == "verified" and payment.decided_by == approver


def test_foreign_invoice_realizes_fx_at_historical_rate(commerce):
    admin = commerce.admin
    update_business_settings(admin, {"enabled_currencies": ["BDT", "USD"]})
    setup.add_rate(
        admin,
        {"currency": "USD", "effective_date": date(2026, 10, 1), "value": "120", "source": "Bank"},
    )
    usd_gl = setup.save_account(
        admin, {"code": "1030", "name": "USD bank", "account_type": "asset", "currency": "USD"}
    )
    usd_bank = banking.save_account(
        admin, {"name": "USD bank", "kind": "bank", "currency": "USD", "gl_account_id": usd_gl.pk}
    )
    customer = save_customer(admin, {"name": "Global Inc", "currency": "USD"})
    invoice = issued(
        commerce,
        customer_id=customer.pk,
        issue_date=date(2026, 10, 2),
        lines=[
            {
                "description": "Export services",
                "unit_price": "1000.00",
                "revenue_account_id": commerce.books.accounts["4100"].pk,
            }
        ],
    )
    assert invoice.base_total == D("120000")
    setup.add_rate(
        admin,
        {"currency": "USD", "effective_date": date(2026, 10, 9), "value": "125", "source": "Bank"},
    )
    half = record(commerce, invoice, "400.00", "usd-payment-1", bank=usd_bank)
    payment = verify(commerce, half)
    rows = {ln.account.code: ln for ln in payment.journal.lines.select_related("account")}
    assert rows["1030"].base_debit == D("50000") and rows["1100"].base_credit == D("48000")
    assert rows["4950"].base_credit == D("2000")
    rest = verify(commerce, record(commerce, invoice, "600.00", "usd-payment-2", bank=usd_bank))
    invoice.refresh_from_db()
    assert invoice.status == "paid" and invoice.base_settled == invoice.base_total
    assert JournalLine.objects.filter(
        journal=rest.journal, account__code="4950"
    ).get().base_credit == D("3000")
    assert_reconciled()
    assert Invoice.objects.get(pk=invoice.pk).snapshot["exchange_rate"] == "120.000000000000"
