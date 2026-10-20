from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction

from apps.billing.models import CreditNote, Refund
from apps.billing.services import credits
from apps.billing.tests.conftest import DAY, as_user, issued
from apps.billing.tests.test_payments import record, verify
from apps.core.exceptions import BusinessRuleViolation

pytestmark = pytest.mark.django_db


def test_credit_note_retries_compare_the_complete_request(commerce):
    invoice = issued(commerce)
    data = {"full": True, "issue_date": DAY, "reason": "Full service credit"}
    actor = as_user(commerce.users.crediter)
    note = credits.request_credit_note(actor, invoice.pk, data, "credit-identity-test")
    assert (
        credits.request_credit_note(actor, str(invoice.pk), data, "credit-identity-test").pk
        == note.pk
    )
    with pytest.raises(BusinessRuleViolation) as error:
        credits.request_credit_note(
            actor, invoice.pk, {**data, "reason": "Different purpose"}, "credit-identity-test"
        )
    assert error.value.get_codes() == "idempotency_conflict"
    assert CreditNote.objects.count() == 1
    with pytest.raises(IntegrityError), transaction.atomic():
        CreditNote.objects.filter(pk=note.pk).update(fingerprint="0" * 64)


def test_refund_and_credit_application_conflicting_keys_are_rejected(commerce):
    invoice = issued(commerce)
    verify(
        commerce,
        record(
            commerce,
            invoice,
            "11000",
            "identity-funded-credit",
            total="12000",
            accept_unapplied=True,
        ),
    )
    actor = as_user(commerce.users.crediter)
    refund_data = {
        "customer_id": commerce.customer.pk,
        "bank_account_id": commerce.bank.pk,
        "amount": "100",
        "refund_date": DAY,
        "reason": "Excess advance",
    }
    refund = credits.request_refund(actor, refund_data, "refund-identity-test")
    assert credits.request_refund(actor, refund_data, "refund-identity-test").pk == refund.pk
    with pytest.raises(BusinessRuleViolation):
        credits.request_refund(actor, {**refund_data, "amount": "200"}, "refund-identity-test")
    with pytest.raises(IntegrityError), transaction.atomic():
        Refund.objects.filter(pk=refund.pk).update(client_key="reused-new-key")
    second = issued(commerce)
    application_data = {"invoice_id": second.pk, "amount": "100", "application_date": DAY}
    recorder = as_user(commerce.users.recorder)
    application = credits.apply_credit(recorder, application_data, "application-identity-test")
    assert (
        credits.apply_credit(recorder, application_data, "application-identity-test").pk
        == application.pk
    )
    with pytest.raises(BusinessRuleViolation):
        credits.apply_credit(
            recorder, {**application_data, "amount": "200"}, "application-identity-test"
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("action", ["credit_note", "refund", "application"])
def test_parallel_credit_requests_have_one_financial_effect(commerce, action):
    from apps.accounting.models import JournalEntry
    from apps.billing.services.reconciliation import receivables

    invoice = issued(commerce)
    verify(
        commerce,
        record(commerce, invoice, "11000", "race-fund", total="12000", accept_unapplied=True),
    )
    actor = as_user(commerce.users.crediter)
    target = issued(commerce) if action == "application" else None

    def operation():
        if action == "credit_note":
            return credits.request_credit_note(
                actor,
                invoice.pk,
                {"full": True, "issue_date": DAY, "reason": "Parallel cancellation"},
                "credit-race",
            )
        if action == "refund":
            return credits.request_refund(
                actor,
                {
                    "customer_id": commerce.customer.pk,
                    "bank_account_id": commerce.bank.pk,
                    "amount": "100",
                    "refund_date": DAY,
                    "reason": "Parallel refund",
                },
                "refund-race",
            )
        return credits.apply_credit(
            as_user(commerce.users.recorder),
            {"invoice_id": target.pk, "amount": "100", "application_date": DAY},
            "application-race",
        )

    barrier = Barrier(2)
    before = JournalEntry.objects.count()

    def attempt(_):
        close_old_connections()
        barrier.wait(timeout=15)
        try:
            return operation().pk
        finally:
            connection.close()

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert results[0] == results[1]
    assert JournalEntry.objects.count() == before + 1
    assert all(value["difference"] == 0 for value in receivables().values())
