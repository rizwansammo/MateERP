from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.accounting.models import AccountingPeriod, JournalEntry
from apps.accounting.services import setup
from apps.approvals import services as approvals
from apps.approvals.models import ApprovalPolicy
from apps.core.exceptions import BusinessRuleViolation
from apps.founders.services import corporate, reports, sharing
from apps.purchasing.models import Expense
from apps.purchasing.services import payables, reconciliation

from .test_corporate import expense, receipt

pytestmark = pytest.mark.django_db


def shared_transfer(f):
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
    transfer = sharing.record_settlement(
        f.request,
        {
            "payer_id": f.b.pk,
            "recipient_id": f.a.pk,
            "date": "2026-02-02",
            "currency": "BDT",
            "amount": "10000",
            "allocations": [{"obligation_id": obligation.pk, "amount": "10000"}],
        },
        "integrity-personal-transfer",
    )
    sharing.confirm_settlement(f.reviewer, transfer.pk, f.b.pk, "authenticated", "Sent")
    sharing.confirm_settlement(f.request, transfer.pk, f.a.pk, "authenticated", "Received")
    return original, obligation, transfer


def reimburse(f, obligation, amount, key="integrity-reimburse"):
    return corporate.record_transaction(
        f.request,
        {
            "kind": "reimbursement",
            "classification": "payable",
            "party_id": obligation.party_id,
            "date": "2026-02-03",
            "currency": "BDT",
            "amount": amount,
            "bank_id": f.bank.pk,
            "allocations": [{"obligation_id": obligation.pk, "amount": amount}],
        },
        key,
    )


def test_recorded_founder_expense_cannot_be_edited_through_purchasing(founder_books):
    f = founder_books
    source = corporate.record_transaction(
        f.request,
        {
            "kind": "expense",
            "classification": "payable",
            "party_id": f.a.pk,
            "date": "2026-02-01",
            "currency": "BDT",
            "expense": {
                "description": "Frozen founder cost",
                "account_id": f.accounts["5100"].pk,
                "amount": "100",
            },
        },
        "integrity-source-frozen",
    )
    with pytest.raises(BusinessRuleViolation, match="owned by Founder Finance"):
        payables.save_expense(
            f.request, {"revision": source.expense.revision, "amount": "200"}, source.expense_id
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        Expense.objects.filter(pk=source.expense_id).update(description="Undisclosed source change")


def test_confirmed_personal_return_unblocks_reimbursement_without_automatic_gl_changes(
    founder_books,
):
    f = founder_books
    receipt(f, "40000")
    original, personal_obligation, transfer = shared_transfer(f)
    before = JournalEntry.objects.count()
    returned = sharing.record_settlement(
        f.request,
        {
            "payer_id": f.a.pk,
            "recipient_id": f.b.pk,
            "date": "2026-02-03",
            "currency": "BDT",
            "amount": "10000",
            "returns_id": transfer.pk,
            "allocations": [{"obligation_id": personal_obligation.pk, "amount": "10000"}],
        },
        "integrity-personal-return",
    )
    sharing.confirm_settlement(f.request, returned.pk, f.a.pk, "authenticated", "Returned")
    sharing.confirm_settlement(f.reviewer, returned.pk, f.b.pk, "authenticated", "Return received")
    assert JournalEntry.objects.count() == before
    assert corporate.outstanding(original.obligation)[0] == 20000
    payout = reimburse(f, original.obligation, "20000")
    corporate.verify(f.reviewer, payout.pk, {})
    assert corporate.outstanding(original.obligation)[0] == 0
    assert all(Decimal(r["difference"]) == 0 for r in reports.reconciliation(f.request))


def test_authorized_liability_reassignment_and_resolution_preserve_total_company_debt(
    founder_books,
):
    f = founder_books
    receipt(f, "40000")
    original, _, transfer = shared_transfer(f)
    reassigned = corporate.record_transaction(
        f.request,
        {
            "kind": "reassign",
            "classification": "payable",
            "party_id": f.a.pk,
            "recipient_id": f.b.pk,
            "date": "2026-02-03",
            "currency": "BDT",
            "amount": "10000",
            "allocations": [{"obligation_id": original.obligation.pk, "amount": "10000"}],
        },
        "integrity-reassignment",
    )
    reassigned = corporate.verify(f.reviewer, reassigned.pk, {})
    corporate.resolve_recovery(
        f.request,
        {
            "obligation_id": original.obligation.pk,
            "settlement_id": transfer.pk,
            "corporate_transaction_id": reassigned.pk,
            "amount": "10000",
            "reason": "Both parties authorize the company owing the personal payer this portion",
        },
    )
    assert corporate.outstanding(original.obligation)[0] == 10000
    assert corporate.outstanding(reassigned.obligation)[0] == 10000
    assert all(Decimal(r["difference"]) == 0 for r in reports.reconciliation(f.request))
    payout = reimburse(f, original.obligation, "10000")
    corporate.verify(f.reviewer, payout.pk, {})
    assert corporate.outstanding(reassigned.obligation)[0] == 10000


def test_founder_payment_settles_existing_ap_without_a_second_expense(founder_books, client_for):
    f = founder_books
    vendor = payables.save_vendor(f.request, {"name": "Existing vendor", "currency": "BDT"})
    bill = payables.save_bill(
        f.request,
        {
            "vendor_id": vendor.pk,
            "vendor_reference": "FND-AP-1",
            "bill_date": date(2026, 2, 1),
            "lines": [
                {
                    "description": "Existing cost",
                    "account_id": f.accounts["5100"].pk,
                    "unit_price": "20000",
                }
            ],
        },
    )
    bill = payables.post_bill(f.request, bill.pk)
    tx = corporate.record_transaction(
        f.request,
        {
            "kind": "vendor_payment",
            "classification": "payable",
            "party_id": f.a.pk,
            "date": "2026-02-02",
            "currency": "BDT",
            "amount": "5000",
            "vendor_allocations": [{"bill_id": bill.pk, "amount": "5000"}],
        },
        "integrity-vendor-settlement",
    )
    tx = corporate.verify(f.reviewer, tx.pk, {})
    bill.refresh_from_db()
    assert bill.outstanding == 15000
    assert not Expense.objects.exists()
    assert not tx.journal.lines.filter(account__account_type="expense").exists()
    assert reconciliation.payables()["difference"] == 0
    response = client_for(f.request.user).get(f"/api/v1/purchasing/vendors/{vendor.pk}/statement/")
    assert response.status_code == 200
    assert Decimal(response.data[-1]["balance"]) == 15000
    corporate.reverse(f.request, tx.pk, "2026-02-03", "Incorrect personal funding evidence")
    assert reconciliation.payables()["difference"] == 0
    response = client_for(f.request.user).get(f"/api/v1/purchasing/vendors/{vendor.pk}/statement/")
    assert Decimal(response.data[-1]["balance"]) == 20000


def test_closed_period_and_rejected_approval_do_not_post_financial_events(founder_books):
    f = founder_books
    obj = corporate.record_transaction(
        f.request,
        {
            "kind": "receipt",
            "classification": "pending",
            "party_id": f.a.pk,
            "date": "2026-02-01",
            "currency": "BDT",
            "amount": "1000",
            "bank_id": f.bank.pk,
        },
        "integrity-approval-source",
    )
    ApprovalPolicy.objects.filter(category="financial_adjustments").update(is_required=True)
    obj = corporate.verify(f.reviewer, obj.pk, {})
    with pytest.raises(IntegrityError), transaction.atomic():
        type(obj.approval).objects.filter(pk=obj.approval_id).update(
            payload={"transaction_id": 999}
        )
    approvals.decide(f.request, obj.approval_id, approve=False, reason="Source evidence invalid")
    obj.refresh_from_db()
    assert obj.status == "rejected"
    assert not JournalEntry.objects.exists()
    ApprovalPolicy.objects.filter(category="financial_adjustments").update(is_required=False)
    period = AccountingPeriod.objects.get(start="2026-02-01")
    setup.set_period(f.request, period.pk, True)
    with pytest.raises(ValidationError, match="open accounting period"):
        receipt(f)
    assert not JournalEntry.objects.exists()


@pytest.mark.parametrize("loan_first", [True, False])
def test_split_liability_reclassification_preserves_the_original_recovery_limit(
    founder_books, loan_first
):
    f = founder_books
    receipt(f, "40000")
    original, _, _ = shared_transfer(f)
    loan = corporate.save_loan(
        f.request, {"party_id": f.a.pk, "name": "Reclassified principal", "currency": "BDT"}
    )
    moved = corporate.record_transaction(
        f.request,
        {
            "kind": "reclassify",
            "classification": "loan",
            "party_id": f.a.pk,
            "date": "2026-02-03",
            "currency": "BDT",
            "amount": "10000",
            "loan_id": loan.pk,
            "allocations": [{"obligation_id": original.obligation.pk, "amount": "10000"}],
        },
        "integrity-split-liability",
    )
    moved = corporate.verify(f.reviewer, moved.pk, {})
    assert moved.obligation.recovery_origin_id == original.pk
    targets = [
        (moved.obligation, "loan_repayment", "loan"),
        (original.obligation, "reimbursement", "payable"),
    ]
    if not loan_first:
        targets.reverse()

    def payout(target, index):
        obligation, kind, classification = target
        return corporate.record_transaction(
            f.request,
            {
                "kind": kind,
                "classification": classification,
                "party_id": f.a.pk,
                "date": "2026-02-04",
                "currency": "BDT",
                "amount": "10000",
                "bank_id": f.bank.pk,
                "allocations": [{"obligation_id": obligation.pk, "amount": "10000"}],
            },
            f"integrity-split-payout-{index}",
        )

    first = payout(targets[0], 0)
    corporate.verify(f.reviewer, first.pk, {})
    with pytest.raises(BusinessRuleViolation, match="duplicate personal recovery"):
        payout(targets[1], 1)
    assert all(Decimal(row["difference"]) == 0 for row in reports.reconciliation(f.request))


def test_rejected_sharing_policy_can_resubmit_and_hidden_changes_cannot_be_approved(founder_books):
    from apps.founders.models import SharingPolicy

    f = founder_books
    ApprovalPolicy.objects.filter(category="admin_changes").update(is_required=True)
    policy = sharing.save_policy(
        f.request,
        {
            "name": "Reviewed policy",
            "basis": "equal",
            "effective_from": "2026-01-01",
            "weights": {str(f.a.pk): "1", str(f.b.pk): "1"},
        },
    )
    policy = sharing.activate(f.request, policy.pk)
    approvals.decide(
        f.reviewer, policy.approval_id, approve=False, reason="Review the allocation terms"
    )
    policy.refresh_from_db()
    assert policy.status == "draft"
    policy = sharing.activate(f.request, policy.pk)
    SharingPolicy.objects.filter(pk=policy.pk).update(name="Changed after submission")
    with pytest.raises(BusinessRuleViolation, match="policy changed"):
        approvals.decide(f.reviewer, policy.approval_id, approve=True)
    policy.refresh_from_db()
    assert policy.status == "pending"
    assert not JournalEntry.objects.exists()
