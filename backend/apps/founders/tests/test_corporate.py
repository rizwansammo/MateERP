from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from apps.accounting.models import JournalEntry
from apps.core.exceptions import BusinessRuleViolation
from apps.founders.models import CorporateTransaction
from apps.founders.services import corporate, reports, sharing

pytestmark = pytest.mark.django_db


def receipt(f, amount="20000", classification="pending", **extra):
    obj = corporate.record_transaction(
        f.request,
        {
            "kind": "receipt",
            "classification": classification,
            "party_id": f.a.pk,
            "date": "2026-02-01",
            "currency": "BDT",
            "amount": amount,
            "bank_id": f.bank.pk,
            **extra,
        },
        f"receipt:{CorporateTransaction.objects.count()}",
    )
    return corporate.verify(f.reviewer, obj.pk, {})


def test_receipt_segregation_replay_and_reconciliation(founder_books):
    f = founder_books
    data = {
        "kind": "receipt",
        "classification": "pending",
        "party_id": f.a.pk,
        "date": "2026-02-01",
        "currency": "BDT",
        "amount": "20000",
        "bank_id": f.bank.pk,
    }
    obj = corporate.record_transaction(f.request, data, "receipt-key-0001")
    assert not JournalEntry.objects.exists()
    with pytest.raises(PermissionDenied):
        corporate.verify(f.request, obj.pk, {})
    assert corporate.record_transaction(f.request, data, "receipt-key-0001").pk == obj.pk
    with pytest.raises(BusinessRuleViolation):
        corporate.record_transaction(f.request, {**data, "amount": "1"}, "receipt-key-0001")
    corporate.verify(f.reviewer, obj.pk, {})
    assert JournalEntry.objects.filter(status="posted").count() == 1
    assert all(Decimal(row["difference"]) == 0 for row in reports.reconciliation(f.request))
    with transaction.atomic(), pytest.raises(IntegrityError):
        CorporateTransaction.objects.filter(pk=obj.pk).update(amount=1)


def test_loan_partial_repayment_no_expense_or_overpayment(founder_books):
    f = founder_books
    loan = corporate.save_loan(
        f.request, {"party_id": f.a.pk, "name": "Founder loan", "currency": "BDT"}
    )
    original = receipt(f, classification="loan", loan_id=loan.pk)
    payout = corporate.record_transaction(
        f.request,
        {
            "kind": "loan_repayment",
            "classification": "loan",
            "party_id": f.a.pk,
            "date": "2026-02-02",
            "currency": "BDT",
            "amount": "5000",
            "bank_id": f.bank.pk,
            "allocations": [{"obligation_id": original.obligation.pk, "amount": "5000"}],
        },
        "loan-repay-0001",
    )
    payout = corporate.verify(f.reviewer, payout.pk, {})
    assert corporate.outstanding(original.obligation)[0] == Decimal("15000")
    assert not payout.journal.lines.filter(account__account_type="expense").exists()
    with pytest.raises(BusinessRuleViolation):
        corporate.record_transaction(
            f.request,
            {
                **payout.request_data,
                "amount": "16000",
                "allocations": [{"obligation_id": original.obligation.pk, "amount": "16000"}],
            },
            "loan-repay-0002",
        )
    assert all(Decimal(row["difference"]) == 0 for row in reports.reconciliation(f.request))


def expense(f):
    obj = corporate.record_transaction(
        f.request,
        {
            "kind": "expense",
            "classification": "payable",
            "party_id": f.a.pk,
            "date": "2026-02-01",
            "currency": "BDT",
            "expense": {
                "description": "Founder-paid hosting",
                "account_id": f.accounts["5100"].pk,
                "amount": "20000",
            },
        },
        "expense-key-0001",
    )
    return corporate.verify(f.reviewer, obj.pk, {})


def test_partial_reimbursement_preserves_exact_company_payable(founder_books):
    f = founder_books
    receipt(f)
    original = expense(f)
    assert original.expense.total == Decimal("20000")
    assert original.expense.journal_id == original.journal_id
    tx = corporate.record_transaction(
        f.request,
        {
            "kind": "reimbursement",
            "classification": "payable",
            "party_id": f.a.pk,
            "date": "2026-02-02",
            "currency": "BDT",
            "amount": "5000",
            "bank_id": f.bank.pk,
            "allocations": [{"obligation_id": original.obligation.pk, "amount": "5000"}],
        },
        "reimburse-key-0001",
    )
    tx = corporate.verify(f.reviewer, tx.pk, {})
    assert corporate.outstanding(original.obligation) == (Decimal("15000"), Decimal("15000"))
    assert not tx.journal.lines.filter(account__account_type="expense").exists()


def test_personal_settlement_does_not_post_and_blocks_double_reimbursement(founder_books):
    f = founder_books
    receipt(f)
    original = expense(f)
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
    shared = sharing.allocate_expense(f.request, {"expense_id": original.expense_id})
    obligation = shared.obligations.get()
    before = JournalEntry.objects.count()
    settlement = sharing.record_settlement(
        f.request,
        {
            "payer_id": f.b.pk,
            "recipient_id": f.a.pk,
            "date": "2026-02-02",
            "currency": "BDT",
            "amount": "10000",
            "allocations": [{"obligation_id": obligation.pk, "amount": "10000"}],
        },
        "personal-key-0001",
    )
    sharing.confirm_settlement(
        f.reviewer, settlement.pk, f.b.pk, "authenticated", "Personal transfer sent"
    )
    sharing.confirm_settlement(f.request, settlement.pk, f.a.pk, "authenticated", "Received")
    assert JournalEntry.objects.count() == before
    assert corporate.outstanding(original.obligation)[0] == Decimal("20000")
    with pytest.raises(BusinessRuleViolation) as error:
        corporate.record_transaction(
            f.request,
            {
                "kind": "reimbursement",
                "classification": "payable",
                "party_id": f.a.pk,
                "date": "2026-02-03",
                "currency": "BDT",
                "amount": "20000",
                "bank_id": f.bank.pk,
                "allocations": [{"obligation_id": original.obligation.pk, "amount": "20000"}],
            },
            "blocked-reimburse-0001",
        )
    assert error.value.get_codes() == "duplicate_recovery_blocked"


def test_rounding_equal_thirds_is_exact_and_stable():
    from apps.founders.services.common import split

    result = split("100.00", "BDT", {"3": "1", "2": "1", "1": "1"})
    assert result == {"3": Decimal("33.33"), "2": Decimal("33.33"), "1": Decimal("33.34")}
