from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException, ValidationError

from apps.accounting.services import posting, setup
from apps.accounting.tests.test_concurrency import race
from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.banking import services
from apps.banking.models import LedgerMatch, Reconciliation, StatementLine
from apps.company.services import update_business_settings

from .test_banking import DAY, banks, statement

pytestmark = pytest.mark.django_db


def foreign_bank(finance):
    request, accounts = finance
    update_business_settings(request, {"enabled_currencies": ["BDT", "USD"]})
    gl = setup.save_account(
        request,
        {"code": "1030", "name": "Dollar ledger", "account_type": "asset", "currency": "USD"},
    )
    bank = services.save_account(
        request,
        {"name": "Dollar account", "kind": "bank", "currency": "USD", "gl_account_id": gl.pk},
    )
    setup.add_rate(
        request, {"currency": "USD", "effective_date": DAY, "value": "120", "source": "Initial"}
    )
    j = posting.save_draft(
        request,
        {
            "posting_date": DAY,
            "description": "Foreign opening",
            "lines": [
                {"account_id": gl.pk, "currency": "USD", "debit": "100"},
                {"account_id": accounts["3010"].pk, "credit": "12000"},
            ],
        },
    )
    posting.post_draft(request, j.pk, "foreign-bank-stock")
    return bank


@pytest.mark.django_db(transaction=True)
def test_competing_foreign_outflows_cannot_overdraw(finance):
    request, accounts = finance
    bank = foreign_bank(finance)
    data = {
        "kind": "withdrawal",
        "bank_account_id": bank.pk,
        "counter_account_id": accounts["6100"].pk,
        "amount": "80",
        "posting_date": DAY,
        "description": "Competing disposal",
    }
    results = race(
        request.user.pk,
        *[
            lambda req, key=k: services.treasury(req, {**data, "posting_key": key}).pk
            for k in ("foreign-withdrawal-a", "foreign-withdrawal-b")
        ],
    )
    assert sum(ok for ok, _ in results) == 1
    assert posting.bank_position(bank.gl_account_id) == (Decimal("20"), Decimal("2400"))


def test_stale_approved_book_value_cannot_be_posted(finance, make_user):
    from types import SimpleNamespace

    request, accounts = finance
    bank = foreign_bank(finance)
    cash = services.save_account(
        request,
        {"name": "Cash", "kind": "cash", "currency": "BDT", "gl_account_id": accounts["1010"].pk},
    )
    policy = ApprovalPolicy.objects.get(category="financial_adjustments")
    policy.is_required = True
    policy.save()
    pending = services.treasury(
        request,
        {
            "posting_key": "pending-foreign-disposal",
            "kind": "withdrawal",
            "bank_account_id": bank.pk,
            "counter_account_id": accounts["6100"].pk,
            "amount": "50",
            "posting_date": DAY,
            "description": "Reviewed at old book value",
        },
    )
    assert pending.status == "pending"
    setup.add_rate(
        request, {"currency": "USD", "effective_date": DAY, "value": "130", "source": "New rate"}
    )
    services.treasury(
        request,
        {
            "posting_key": "intervening-foreign-receipt",
            "kind": "transfer",
            "bank_account_id": cash.pk,
            "destination_id": bank.pk,
            "amount": "13000",
            "received_amount": "100",
            "posting_date": DAY,
            "description": "New book value",
        },
    )
    approver = SimpleNamespace(user=make_user("fx_approver", "administrator"), META={})
    with pytest.raises(APIException, match="Book value changed"):
        decide(approver, pending.approval_id, approve=True)
    pending.refresh_from_db()
    assert pending.status == "pending" and pending.approval.status == "pending"
    assert posting.bank_position(bank.gl_account_id) == (Decimal("200"), Decimal("25000"))


def transfer(request, cash, bank, key="integrity-transfer", amount="250"):
    return services.treasury(
        request,
        {
            "posting_key": key,
            "kind": "transfer",
            "bank_account_id": cash.pk,
            "destination_id": bank.pk,
            "amount": amount,
            "posting_date": DAY,
            "description": "Bank transfer",
        },
    )


def test_bank_charge_and_interest_affect_one_ledger(finance):
    r, a = finance
    cash, _ = banks(finance)
    for kind, code, amount in (("charge", "6200", "10"), ("interest", "4900", "3")):
        j = services.treasury(
            r,
            {
                "posting_key": f"bank-{kind}-integrity",
                "kind": kind,
                "bank_account_id": cash.pk,
                "amount": amount,
                "counter_account_id": a[code].pk,
                "posting_date": DAY,
                "description": kind,
            },
        )
        assert j.lines.count() == 2 and j.status == "posted"
    assert posting.bank_position(cash.gl_account_id)[0] == 993
    with pytest.raises(ValidationError):
        services.treasury(
            r,
            {
                "posting_key": "invalid-charge-offset",
                "kind": "charge",
                "bank_account_id": cash.pk,
                "amount": "10",
                "counter_account_id": a["3010"].pk,
                "posting_date": DAY,
                "description": "Not an expense",
            },
        )


def test_stale_treasury_quote_and_balanced_preview(finance):
    r, a = finance
    cash, bank = banks(finance)
    data = {
        "posting_key": "preview-snapshot-integrity",
        "kind": "transfer",
        "bank_account_id": cash.pk,
        "destination_id": bank.pk,
        "amount": "50",
        "posting_date": DAY,
        "description": "Preview",
    }
    quote = services.treasury(r, data, preview=True)
    assert (
        sum(Decimal(line["base_debit"]) - Decimal(line["base_credit"]) for line in quote["lines"])
        == 0
    )
    with pytest.raises(APIException):
        services.treasury(r, {**data, "quote_fingerprint": "0" * 64})
    j = services.treasury(r, {**data, "quote_fingerprint": quote["quote_fingerprint"]})
    assert j.status == "posted"


def test_completed_statement_and_evidence_reject_direct_mutation(finance):
    r, _ = finance
    cash, bank = banks(finance)
    j = transfer(r, cash, bank)
    rec = statement(finance, bank)
    s = rec.statement.lines.first()
    services.match(r, rec.pk, [s.pk], [j.lines.get(account_id=bank.gl_account_id).pk])
    services.complete(r, rec.pk)
    with pytest.raises(APIException, match="Reopen"):
        transfer(r, cash, bank, key="late-backdated-transfer", amount="1")
    for operation in (
        lambda: StatementLine.objects.filter(pk=s.pk).update(amount=Decimal("251")),
        lambda: StatementLine.objects.filter(pk=s.pk).delete(),
        lambda: Reconciliation.objects.filter(pk=rec.pk).update(evidence=[]),
        lambda: posting.reverse(r, j.pk, DAY, "Matched reversal", "matched-reversal-key"),
    ):
        with pytest.raises((IntegrityError, APIException)), transaction.atomic():
            operation()


def test_initial_nonzero_statement_opening_and_empty_month(finance):
    request, _ = finance
    _, bank = banks(finance)
    # A first statement can start after the migration balance; it is a documented
    # baseline, not an outstanding receipt to double count.
    cash = services.BankAccount.objects.get(kind="cash")
    transfer(request, cash, bank)
    rec = services.create_statement(
        request,
        {
            "bank_account_id": bank.pk,
            "reference": "November",
            "start": date(2026, 11, 1),
            "end": date(2026, 11, 30),
            "opening_balance": "250",
            "closing_balance": "250",
            "lines": [],
        },
    )
    assert services.reconciliation_summary(rec)["difference"] == "0.000000"
    assert services.complete(request, rec.pk).is_complete


def test_statement_arithmetic_and_date_validation(finance):
    r, _ = finance
    _, bank = banks(finance)
    data = {
        "bank_account_id": bank.pk,
        "reference": "Invalid",
        "start": date(2026, 10, 1),
        "end": date(2026, 10, 31),
        "opening_balance": "0",
        "closing_balance": "100",
        "lines": [{"date": DAY, "description": "One line", "amount": "99"}],
    }
    with pytest.raises(ValidationError):
        services.create_statement(r, data)
    data["lines"][0]["amount"] = "100"
    data["lines"][0]["date"] = date(2026, 11, 1)
    with pytest.raises(ValidationError):
        services.create_statement(r, data)
    assert not Reconciliation.objects.exists()


def test_automatch_skips_equal_amount_ambiguity(finance):
    r, _ = finance
    cash, bank = banks(finance)
    transfer(r, cash, bank, "ambiguous-transfer-one")
    transfer(r, cash, bank, "ambiguous-transfer-two")
    rec = statement(finance, bank)
    assert services.auto_match(r, rec.pk) == 0
    assert not LedgerMatch.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_competing_reconciliation_matches_consume_line_once(finance):
    r, _ = finance
    cash, bank = banks(finance)
    j = transfer(r, cash, bank)
    rec = statement(finance, bank)
    sid = rec.statement.lines.first().pk
    lid = j.lines.get(account_id=bank.gl_account_id).pk
    results = race(
        r.user.pk,
        lambda req: services.match(req, rec.pk, [sid], [lid]).pk,
        lambda req: services.match(req, rec.pk, [sid], [lid]).pk,
    )
    assert sum(ok for ok, _ in results) == 1
    assert LedgerMatch.objects.filter(line_id=lid, is_active=True).count() == 1
