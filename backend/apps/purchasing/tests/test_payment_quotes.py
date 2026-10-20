from datetime import date

import pytest
from rest_framework.exceptions import ValidationError

from apps.accounting.models import JournalEntry
from apps.accounting.services import setup
from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.banking import services as banking
from apps.billing.tests.conftest import DAY
from apps.company.services import update_business_settings
from apps.core.exceptions import BusinessRuleViolation
from apps.purchasing.models import VendorPayment
from apps.purchasing.services import payables, payments

pytestmark = pytest.mark.django_db


def foreign_payment(commerce, initial_rate="130"):
    actor = commerce.admin
    update_business_settings(actor, {"enabled_currencies": ["BDT", "USD"]})
    setup.add_rate(
        actor,
        {
            "currency": "USD",
            "effective_date": date(2026, 10, 1),
            "value": initial_rate,
            "source": "Funding",
        },
    )
    account = setup.save_account(
        actor, {"code": "1044", "name": "Quote USD", "account_type": "asset", "currency": "USD"}
    )
    bank = banking.save_account(
        actor, {"name": "Quote USD", "kind": "bank", "currency": "USD", "gl_account_id": account.pk}
    )
    banking.treasury(
        actor,
        {
            "posting_key": "quote-initial-funding",
            "kind": "deposit",
            "bank_account_id": bank.pk,
            "posting_date": date(2026, 10, 1),
            "amount": "200",
            "counter_account_id": commerce.books.accounts["3010"].pk,
            "description": "Initial funding",
        },
    )
    setup.add_rate(
        actor, {"currency": "USD", "effective_date": DAY, "value": "120", "source": "Invoice rate"}
    )
    vendor = payables.save_vendor(actor, {"name": "Quote supplier", "currency": "USD"})
    bill = payables.save_bill(
        actor,
        {
            "vendor_id": vendor.pk,
            "vendor_reference": "QUOTE-BILL",
            "bill_date": DAY,
            "currency": "USD",
            "lines": [
                {
                    "description": "Service",
                    "unit_price": "100",
                    "account_id": commerce.books.accounts["6100"].pk,
                }
            ],
        },
    )
    payables.post_bill(actor, bill.pk)
    return {
        "vendor_id": vendor.pk,
        "bank_account_id": bank.pk,
        "payment_date": DAY,
        "amount": "100",
        "allocations": [{"bill_id": bill.pk, "amount": "100"}],
    }


def test_fx_confirmation_requires_the_reviewed_quote(commerce):
    data = foreign_payment(commerce)
    before = JournalEntry.objects.count()
    with pytest.raises(ValidationError) as error:
        payments.pay(commerce.admin, {**data, "confirm_fx": True}, "missing-fx-quote")
    assert "quote_fingerprint" in error.value.detail
    assert not VendorPayment.objects.exists() and JournalEntry.objects.count() == before
    quote = payments.preview(commerce.admin, data)
    with pytest.raises(ValidationError) as error:
        payments.pay(
            commerce.admin,
            {**data, "quote_fingerprint": quote["quote_fingerprint"]},
            "unconfirmed-fx",
        )
    assert "confirm_fx" in error.value.detail
    result = payments.pay(
        commerce.admin,
        {**data, "quote_fingerprint": quote["quote_fingerprint"], "confirm_fx": True},
        "confirmed-fx-quote",
    )
    assert result.status == "paid"


@pytest.mark.parametrize("initial_rate", ["120", "130"])
def test_approval_cannot_silently_accept_a_changed_carrying_value(commerce, initial_rate):
    data = foreign_payment(commerce, initial_rate)
    policy = ApprovalPolicy.objects.get(category="vendor_payments")
    policy.is_required = True
    policy.allow_self_approval = True
    policy.save()
    quote = payments.preview(commerce.admin, data)
    pending = payments.pay(
        commerce.admin,
        {**data, "quote_fingerprint": quote["quote_fingerprint"], "confirm_fx": True},
        "pending-reviewed-fx",
    )
    assert pending.journal_id is None
    assert pending.approval.payload["data"]["quote_fingerprint"] == quote["quote_fingerprint"]
    setup.add_rate(
        commerce.admin,
        {"currency": "USD", "effective_date": DAY, "value": "135", "source": "New funding"},
    )
    banking.treasury(
        commerce.admin,
        {
            "posting_key": "quote-additional-funding",
            "kind": "deposit",
            "bank_account_id": data["bank_account_id"],
            "posting_date": DAY,
            "amount": "100",
            "counter_account_id": commerce.books.accounts["3010"].pk,
            "description": "Additional funding changes carrying value",
        },
    )
    before = JournalEntry.objects.count()
    with pytest.raises(BusinessRuleViolation) as error:
        decide(commerce.admin, pending.approval_id, approve=True)
    assert error.value.get_codes() == "stale_quote"
    pending.refresh_from_db()
    pending.approval.refresh_from_db()
    assert pending.journal_id is None and pending.approval.status == "pending"
    assert JournalEntry.objects.count() == before


def test_unchanged_reviewed_quote_can_be_approved(commerce):
    data = foreign_payment(commerce)
    policy = ApprovalPolicy.objects.get(category="vendor_payments")
    policy.is_required = True
    policy.allow_self_approval = True
    policy.save()
    quote = payments.preview(commerce.admin, data)
    pending = payments.pay(
        commerce.admin,
        {**data, "quote_fingerprint": quote["quote_fingerprint"], "confirm_fx": True},
        "unchanged-approved-quote",
    )
    decide(commerce.admin, pending.approval_id, approve=True)
    pending.refresh_from_db()
    assert pending.status == "paid" and pending.journal_id
