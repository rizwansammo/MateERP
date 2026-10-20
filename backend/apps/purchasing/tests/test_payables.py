"""Scenarios I, J, K, M: vendor bills, vendor payments, expenses, recurring expenses, AP."""

from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import APIException, PermissionDenied

from apps.accounting.models import JournalLine
from apps.accounting.services import setup
from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.banking import services as banking
from apps.company.services import update_business_settings
from apps.purchasing.models import Expense, VendorBill
from apps.purchasing.services import payables, payments, reconciliation, recurring

pytestmark = pytest.mark.django_db
DAY = date(2026, 10, 10)


def act(user):
    return SimpleNamespace(user=user, META={})


@pytest.fixture
def buying(books, user_with):
    admin = books.request
    bank = banking.save_account(
        admin,
        {
            "name": "Operating bank",
            "kind": "bank",
            "currency": "BDT",
            "gl_account_id": books.accounts["1020"].pk,
        },
    )
    clerk = user_with("buyer", "finance.view", "vendors.manage", "bills.manage", "expenses.manage")
    payer = user_with("payer", "finance.view", "vendor_payments.manage")
    vendor = payables.save_vendor(
        act(clerk), {"name": "Cloud Hosting Ltd", "currency": "BDT", "payment_terms_days": 15}
    )
    return SimpleNamespace(
        books=books, admin=admin, bank=bank, clerk=clerk, payer=payer, vendor=vendor
    )


def bill(buying, reference="INV-77", amount="10000", tax=True, **extra):
    row = {
        "description": "VPS hosting",
        "unit_price": amount,
        "account_id": buying.books.accounts["6100"].pk,
    }
    if tax:
        row["tax_code_id"] = buying.books.vat.pk
    return payables.save_bill(
        act(buying.clerk),
        {
            "vendor_id": buying.vendor.pk,
            "vendor_reference": reference,
            "bill_date": DAY,
            "lines": [row],
            **extra,
        },
    )


def lines(journal):
    return sorted(
        (x.account.code, x.debit, x.credit) for x in journal.lines.select_related("account")
    )


def assert_ap_reconciled():
    result = reconciliation.payables()
    assert result["difference"] == 0, result
    return result


def test_bill_posts_expense_input_tax_and_payable(buying):
    posted = payables.post_bill(act(buying.clerk), bill(buying).pk)
    assert posted.number == "BILL-2026-001" and posted.status == "posted"
    assert lines(posted.journal) == [
        ("1150", D("1000"), 0),
        ("2010", 0, D("11000")),
        ("6100", D("10000"), 0),
    ]
    assert posted.journal.source_type == "vendor_bill"
    assert assert_ap_reconciled()["ledger"] == D("11000")


def test_duplicate_vendor_invoice_is_blocked(buying):
    bill(buying, reference="INV-77")
    with pytest.raises(APIException) as dup:
        bill(buying, reference="inv 77")
    assert dup.value.get_codes() == "duplicate_vendor_invoice"
    other = payables.save_vendor(act(buying.clerk), {"name": "Other Vendor", "currency": "BDT"})
    assert payables.save_bill(
        act(buying.clerk),
        {
            "vendor_id": other.pk,
            "vendor_reference": "INV-77",
            "bill_date": DAY,
            "lines": [
                {
                    "description": "x",
                    "unit_price": "1",
                    "account_id": buying.books.accounts["6100"].pk,
                }
            ],
        },
    ).pk


def test_vendor_payment_partial_then_full_and_reversal(buying):
    posted = payables.post_bill(act(buying.clerk), bill(buying).pk)
    data = {
        "vendor_id": buying.vendor.pk,
        "bank_account_id": buying.bank.pk,
        "payment_date": DAY,
        "amount": "4000",
        "allocations": [{"bill_id": posted.pk, "amount": "4000"}],
    }
    first = payments.pay(act(buying.payer), data, "vendor-pay-1")
    assert lines(first.journal) == [("1020", 0, D("4000")), ("2010", D("4000"), 0)]
    assert payments.pay(act(buying.payer), data, "vendor-pay-1").pk == first.pk
    posted.refresh_from_db()
    assert posted.status == "partially_paid"
    with pytest.raises(APIException):
        payments.pay(
            act(buying.payer),
            {**data, "amount": "8000", "allocations": [{"bill_id": posted.pk, "amount": "8000"}]},
            "vendor-pay-2",
        )
    payments.pay(
        act(buying.payer),
        {**data, "amount": "7000", "allocations": [{"bill_id": posted.pk, "amount": "7000"}]},
        "vendor-pay-3",
    )
    posted.refresh_from_db()
    assert posted.status == "paid" and posted.base_settled == posted.base_total
    assert assert_ap_reconciled()["ledger"] == 0
    payments.reverse(act(buying.payer), first.pk, "Payment returned")
    posted.refresh_from_db()
    assert posted.status == "partially_paid" and posted.outstanding == D("4000")
    assert_ap_reconciled()
    with pytest.raises(PermissionDenied):
        payments.pay(act(buying.clerk), data, "clerk-cannot-pay")


def test_paid_and_accrued_expenses_never_double_count(buying):
    clerk = act(buying.clerk)
    paid = payables.save_expense(
        clerk,
        {
            "description": "Software subscription",
            "expense_date": DAY,
            "payment_mode": "paid",
            "bank_account_id": buying.bank.pk,
            "account_id": buying.books.accounts["6100"].pk,
            "amount": "1100",
            "tax_code_id": buying.books.vat.pk,
            "prices_include_tax": True,
        },
    )
    paid = payables.post_expense(clerk, paid.pk)
    assert paid.status == "paid" and (paid.taxable, paid.tax) == (D("1000"), D("100"))
    assert lines(paid.journal) == [
        ("1020", 0, D("1100")),
        ("1150", D("100"), 0),
        ("6100", D("1000"), 0),
    ]
    accrued = payables.save_expense(
        clerk,
        {
            "description": "Office cleaning",
            "expense_date": DAY,
            "payment_mode": "accrued",
            "vendor_id": buying.vendor.pk,
            "account_id": buying.books.accounts["6100"].pk,
            "amount": "500",
        },
    )
    accrued = payables.post_expense(clerk, accrued.pk)
    assert accrued.status == "posted" and lines(accrued.journal) == [
        ("2010", 0, D("500")),
        ("6100", D("500"), 0),
    ]
    # A paid-now expense never enters payables, so it cannot be paid twice.
    with pytest.raises(APIException):
        payments.pay(
            act(buying.payer),
            {
                "vendor_id": buying.vendor.pk,
                "bank_account_id": buying.bank.pk,
                "amount": "1100",
                "allocations": [{"expense_id": paid.pk, "amount": "1100"}],
            },
            "pay-paid-expense",
        )
    payments.pay(
        act(buying.payer),
        {
            "vendor_id": buying.vendor.pk,
            "bank_account_id": buying.bank.pk,
            "payment_date": DAY,
            "amount": "500",
            "allocations": [{"expense_id": accrued.pk, "amount": "500"}],
        },
        "pay-accrued-1",
    )
    accrued.refresh_from_db()
    assert accrued.status == "paid"
    expense_total = sum(
        x.debit
        for x in JournalLine.objects.filter(
            account=buying.books.accounts["6100"], journal__status="posted"
        )
    )
    assert expense_total == D("1500")
    assert_ap_reconciled()
    with pytest.raises(APIException):
        payables.save_expense(
            clerk,
            {
                "description": "Founder card",
                "expense_date": DAY,
                "payment_mode": "paid",
                "bank_account_id": buying.bank.pk,
                "amount": "1",
                "paid_by": "founder",
            },
        )


def test_expense_approval_threshold(buying, user_with):
    policy = ApprovalPolicy.objects.get(category="expenses")
    policy.is_required = True
    policy.amount_threshold = D("1000")
    approver = user_with("approver", "finance.view", "expenses.manage")
    policy.approver_role = approver.role
    policy.save()
    clerk = act(buying.clerk)
    big = payables.save_expense(
        clerk,
        {
            "description": "Laptop",
            "expense_date": DAY,
            "payment_mode": "paid",
            "bank_account_id": buying.bank.pk,
            "account_id": buying.books.accounts["6100"].pk,
            "amount": "5000",
        },
    )
    big = payables.post_expense(clerk, big.pk)
    assert big.status == "awaiting_approval" and big.journal is None
    with pytest.raises(PermissionDenied):
        decide(clerk, big.approval_id, approve=True)
    decide(act(approver), big.approval_id, approve=True)
    big.refresh_from_db()
    assert big.status == "paid" and big.posted_by == approver


def test_foreign_vendor_payment_uses_carrying_value_and_quote(buying):
    admin = buying.admin
    update_business_settings(admin, {"enabled_currencies": ["BDT", "USD"]})
    setup.add_rate(
        admin,
        {"currency": "USD", "effective_date": date(2026, 10, 1), "value": "120", "source": "Bank"},
    )
    usd_gl = setup.save_account(
        admin, {"code": "1030", "name": "USD bank", "account_type": "asset", "currency": "USD"}
    )
    usd = banking.save_account(
        admin, {"name": "USD bank", "kind": "bank", "currency": "USD", "gl_account_id": usd_gl.pk}
    )
    banking.treasury(
        admin,
        {
            "posting_key": "usd-funding-1",
            "kind": "deposit",
            "bank_account_id": usd.pk,
            "posting_date": date(2026, 10, 1),
            "amount": "500",
            "counter_account_id": buying.books.accounts["3010"].pk,
            "description": "Funding",
        },
    )
    vendor = payables.save_vendor(act(buying.clerk), {"name": "US SaaS Inc", "currency": "USD"})
    posted = payables.post_bill(
        act(buying.clerk),
        payables.save_bill(
            act(buying.clerk),
            {
                "vendor_id": vendor.pk,
                "vendor_reference": "US-1",
                "bill_date": date(2026, 10, 2),
                "lines": [
                    {
                        "description": "Licence",
                        "unit_price": "100",
                        "account_id": buying.books.accounts["6100"].pk,
                    }
                ],
            },
        ).pk,
    )
    assert posted.base_total == D("12000")
    setup.add_rate(
        admin,
        {"currency": "USD", "effective_date": date(2026, 10, 5), "value": "125", "source": "Bank"},
    )
    data = {
        "vendor_id": vendor.pk,
        "bank_account_id": usd.pk,
        "payment_date": DAY,
        "amount": "100",
        "allocations": [{"bill_id": posted.pk, "amount": "100"}],
    }
    quote = payments.preview(act(buying.payer), data)
    # Cash leaves at its 120 carrying value: no FX difference against the 120 bill.
    assert D(quote["fx_difference"]) == 0
    paid = payments.pay(
        act(buying.payer), {**data, "quote_fingerprint": quote["quote_fingerprint"]}, "usd-vendor-1"
    )
    rows = {x.account.code: x for x in paid.journal.lines.select_related("account")}
    assert rows["2010"].base_debit == D("12000") and rows["1030"].base_credit == D("12000")
    with pytest.raises(APIException) as stale:
        payments.pay(
            act(buying.payer),
            {**data, "amount": "1", "allocations": [], "quote_fingerprint": "0" * 64},
            "usd-vendor-2",
        )
    assert stale.value.status_code in (400, 409)
    assert_ap_reconciled()
    assert VendorBill.objects.get(pk=posted.pk).status == "paid"


def test_recurring_expenses_generate_idempotent_drafts(buying):
    clerk = act(buying.clerk)
    schedule = recurring.save_schedule(
        clerk,
        {
            "name": "VPS",
            "vendor_id": buying.vendor.pk,
            "frequency": "monthly",
            "start_date": date(2026, 8, 31),
            "description": "VPS hosting",
            "amount": "2500",
            "payment_mode": "accrued",
            "account_id": buying.books.accounts["6100"].pk,
        },
    )
    first = recurring.run_due(date(2026, 10, 10), runner=buying.clerk)
    assert [r["status"] for r in first] == ["drafted", "drafted"]
    assert sorted(Expense.objects.values_list("expense_date", flat=True)) == [
        date(2026, 8, 31),
        date(2026, 9, 30),
    ]
    assert recurring.run_due(date(2026, 10, 10), runner=buying.clerk) == []
    schedule.refresh_from_db()
    assert schedule.next_run_date == date(2026, 10, 31)
    recurring.set_status(clerk, schedule.pk, "paused")
    assert recurring.run_due(date(2026, 12, 31), runner=buying.clerk) == []
    assert Expense.objects.filter(status="draft").count() == 2
