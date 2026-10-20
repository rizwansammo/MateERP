from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from rest_framework.exceptions import APIException, ValidationError

from apps.accounting import reports
from apps.accounting.models import (
    Account,
    AccountingPeriod,
    JournalEntry,
    JournalLine,
    PostingIdentity,
)
from apps.accounting.money import money
from apps.accounting.services import posting, setup
from apps.accounts.models import Permission, Role, User
from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.company.models import CompanyProfile
from apps.company.services import update_company

pytestmark = pytest.mark.django_db
DAY = date(2026, 10, 10)


def draft(finance, debit="100.00", credit="100.00", **extra):
    request, accounts = finance
    return posting.save_draft(
        request,
        {
            "posting_date": DAY,
            "description": "Capital contribution",
            "lines": [
                {"account_id": accounts["1010"].pk, "debit": debit},
                {"account_id": accounts["3010"].pk, "credit": credit},
            ],
            **extra,
        },
    )


def post(finance, debit="100.00", credit="100.00", key="test-posting-key", **extra):
    j = draft(finance, debit, credit, **extra)
    return posting.post_draft(finance[0], j.pk, key)[0]


def test_balanced_post_replay_and_ledger(finance):
    r, a = finance
    j = post(finance)
    assert j.number == "JV-2026-0001"
    assert posting.post_draft(r, j.pk, "test-posting-key")[1]
    assert JournalEntry.objects.filter(status="posted").count() == 1
    posting.post_draft(r, j.pk, "second-observed-client-key")
    with pytest.raises(APIException):
        posting.post_draft(r, draft(finance).pk, "second-observed-client-key")
    result = reports.ledger(a["1010"].pk, DAY, DAY)
    assert Decimal(result["closing"]) == 100
    tb = reports.report("tb", DAY, DAY)
    assert tb["balanced"] and Decimal(tb["total_debits"]) == 100


def test_unbalanced_has_no_partial_posting(finance):
    j = draft(finance, "100", "99")
    with pytest.raises(ValidationError):
        posting.post_draft(finance[0], j.pk, "bad-post-key")
    j.refresh_from_db()
    assert j.status == "draft" and not j.number
    assert not PostingIdentity.objects.exists()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0.001", 1.1, True])
def test_invalid_amounts_rejected(value):
    with pytest.raises(ValidationError):
        money(value, "BDT")


def test_currency_precision():
    assert money("123", "JPY") == 123
    with pytest.raises(ValidationError):
        money("123.01", "JPY")


def test_summary_and_inactive_rejected(finance):
    r, a = finance
    for account in (a["1000"], a["1010"]):
        if account.is_postable:
            setup.save_account(r, {"is_active": False}, account.pk)
        with pytest.raises(ValidationError):
            posting.save_draft(
                r,
                {
                    "posting_date": DAY,
                    "description": "Invalid",
                    "lines": [{"account_id": account.pk, "debit": "1"}],
                },
            )


def test_posted_immutability_service_and_sql(finance):
    r, a = finance
    j = post(finance)
    for operation in [
        lambda: JournalEntry.objects.filter(pk=j.pk).update(description="Changed"),
        lambda: j.lines.update(debit=Decimal("999")),
        lambda: j.lines.all().delete(),
        lambda: JournalLine.objects.create(
            journal=j,
            position=9,
            account=a["1010"],
            currency="BDT",
            debit=1,
            credit=0,
            base_debit=1,
            base_credit=0,
        ),
    ]:
        with pytest.raises(IntegrityError), transaction.atomic():
            operation()
    with pytest.raises(APIException):
        posting.save_draft(r, {"revision": 1}, j.pk)


def test_raw_sql_unbalanced_post_is_rejected(finance):
    j = draft(finance, "10", "9")
    p = AccountingPeriod.objects.get(start=date(2026, 10, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        JournalEntry.objects.filter(pk=j.pk).update(
            status="posted",
            number="RAW-1",
            period=p,
            posted_by=finance[0].user,
            posted_at="2026-10-10T12:00:00Z",
        )
        with connection.cursor() as cur:
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_reversal_exact_and_original_untouched(finance):
    r, _ = finance
    j = post(finance)
    original = posting.snapshot(j)
    reversal = posting.reverse(r, j.pk, date(2026, 11, 1), "Correct original", "reversal-test-key")
    j.refresh_from_db()
    assert posting.snapshot(j) == original
    assert reversal.reversal_of_id == j.pk
    assert Decimal(reports.report("tb", DAY, date(2026, 12, 31))["total_debits"]) == 0
    assert (
        posting.reverse(r, j.pk, date(2026, 11, 1), "Correct original", "reversal-test-key").pk
        == reversal.pk
    )


def test_period_and_history_locks(finance):
    r, _ = finance
    j = post(finance)
    period = AccountingPeriod.objects.get(pk=j.period_id)
    setup.set_period(r, period.pk, True)
    with pytest.raises(ValidationError):
        posting.post_draft(r, draft(finance).pk, "late-post-key")
    with pytest.raises(APIException):
        update_company(r, {"base_currency": "USD"})
    with pytest.raises(APIException):
        update_company(r, {"fiscal_year_start_month": 7})
    with pytest.raises(IntegrityError), transaction.atomic():
        CompanyProfile.objects.filter(pk=1).update(base_currency="USD")
    with pytest.raises(ValidationError):
        setup.set_period(r, period.pk, False)
    setup.set_period(r, period.pk, False, "Audited reopening")
    assert posting.post_draft(r, draft(finance).pk, "new-open-key")[0].status == "posted"


def test_hierarchy_and_historical_meaning(finance):
    r, a = finance
    with pytest.raises(ValidationError):
        setup.save_account(r, {"parent_id": a["5000"].pk}, a["1000"].pk)
    with pytest.raises(ValidationError):
        setup.save_account(r, {"parent_id": a["1010"].pk}, a["1000"].pk)
    post(finance)
    with pytest.raises(APIException):
        setup.save_account(r, {"account_type": "revenue"}, a["1010"].pk)
    with pytest.raises(IntegrityError), transaction.atomic():
        Account.objects.filter(pk=a["1010"].pk).update(account_type="revenue")


def test_fiscal_boundaries_and_overlap(finance):
    r, _ = finance
    with pytest.raises(APIException):
        setup.create_year(r, date(2026, 1, 1))
    with pytest.raises(ValidationError):
        setup.create_year(r, date(2027, 2, 1))
    assert setup.create_year(r, date(2027, 1, 1)).periods.count() == 12


def test_opening_duplicate_is_rejected(finance):
    first = post(finance, kind="opening")
    with pytest.raises(IntegrityError), transaction.atomic():
        draft(finance, kind="opening")
    assert first.status == "posted"


def test_conflicting_key_and_source_reuse(finance):
    r, a = finance
    post(finance)
    other = draft(finance, "90", "90")
    with pytest.raises(APIException):
        posting.post_draft(r, other.pk, "test-posting-key")
    args = dict(
        actor=r.user,
        posting_key="adapter-test-key",
        source_type="integration_test",
        source_id="abc",
        source_action="post",
        posting_date=DAY,
        description="Adapter",
        lines=[
            {"account_id": a["1010"].pk, "debit": "10"},
            {"account_id": a["3010"].pk, "credit": "10"},
        ],
    )
    j = posting.post_journal(**args)
    assert posting.post_journal(**args).pk == j.pk
    with pytest.raises(APIException):
        posting.post_journal(**{**args, "description": "Changed"})


def test_financial_approvals_snapshot_threshold(finance, make_user):
    r, a = finance
    approver = make_user("approver", "administrator")
    policy = ApprovalPolicy.objects.get(category="financial_adjustments")
    policy.is_required = True
    policy.amount_threshold = 50
    policy.save()
    j = post(finance)
    assert j.status == "pending"
    with pytest.raises(APIException):
        decide(r, j.approval_id, approve=True)
    second = post(finance, key="second-approval-key")
    assert second.approval_id != j.approval_id
    with pytest.raises(APIException):
        posting.save_draft(r, {"revision": 1}, j.pk)
    decide(SimpleNamespace(user=approver, META={}), j.approval_id, approve=True)
    j.refresh_from_db()
    assert j.status == "posted"


@pytest.mark.parametrize("change", ["permission", "password"])
def test_approval_rechecks_requester_access(finance, make_user, change):
    admin_request, accounts = finance
    role = Role.objects.create(key="posting-requester", name="Posting requester")
    role.permissions.set(Permission.objects.filter(code__in=["finance.view", "accounting.manage"]))
    user = make_user("posting_requester", None)
    user.role = role
    user.save()
    request = SimpleNamespace(user=user, META={})
    policy = ApprovalPolicy.objects.get(category="financial_adjustments")
    policy.is_required = True
    policy.save()
    journal = post((request, accounts))
    if change == "permission":
        role.permissions.remove(Permission.objects.get(code="finance.view"))
    else:
        User.objects.filter(pk=user.pk).update(must_change_password=True)
    with pytest.raises(APIException) as denied:
        decide(admin_request, journal.approval_id, approve=True)
    assert denied.value.status_code == 403
    journal.refresh_from_db()
    assert journal.status == "pending" and journal.approval.status == "pending"


def test_reports_mathematical_identity(finance):
    r, a = finance
    post(finance, "1000", "1000")
    for i, (account, d, c) in enumerate([("4100", "250", "250"), ("6100", "40", "40")]):
        lines = (
            [{"account_id": a["1010"].pk, "debit": d}, {"account_id": a[account].pk, "credit": c}]
            if account == "4100"
            else [
                {"account_id": a[account].pk, "debit": d},
                {"account_id": a["1010"].pk, "credit": c},
            ]
        )
        j = posting.save_draft(r, {"posting_date": DAY, "description": "Activity", "lines": lines})
        posting.post_draft(r, j.pk, f"activity-key-{i}")
    pnl = reports.report("pnl", date(2026, 1, 1), DAY)
    bs = reports.report("bs", date(2026, 1, 1), DAY)
    assert Decimal(pnl["net_profit"]) == 210
    assert Decimal(bs["assets"]) == 1210 and bs["balanced"]
    assert Decimal(bs["equity"]) == 1210


@pytest.mark.django_db(transaction=True)
def test_simultaneous_same_key_creates_one_posting(finance):
    r, _ = finance
    j = draft(finance)
    barrier = Barrier(2)
    user_id = r.user.pk

    def worker():
        close_old_connections()
        try:
            req = SimpleNamespace(user=User.objects.select_related("role").get(pk=user_id), META={})
            barrier.wait(timeout=10)
            return posting.post_draft(req, j.pk, "concurrent-same-key")[0].pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: worker(), range(2)))
    assert ids[0] == ids[1]
    assert JournalEntry.objects.filter(status="posted").count() == 1
