"""Real independent PostgreSQL connections competing for financial state."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from types import SimpleNamespace

import pytest
from django.db import close_old_connections, connections
from rest_framework.exceptions import APIException

from apps.accounting.models import Account, AccountingPeriod, JournalEntry
from apps.accounting.services import posting, setup
from apps.accounts.models import User
from apps.company.models import CompanyProfile
from apps.company.services import update_company

from .test_engine import DAY, draft, post

pytestmark = pytest.mark.django_db(transaction=True)


def race(user_id, *operations):
    barrier = Barrier(len(operations))

    def work(fn):
        close_old_connections()
        try:
            request = SimpleNamespace(
                user=User.objects.select_related("role").get(pk=user_id), META={}
            )
            barrier.wait(timeout=15)
            try:
                return True, fn(request)
            except APIException as exc:
                return False, exc
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        return list(pool.map(work, operations))


def test_conflicting_posting_key_has_one_winner(finance):
    r, _ = finance
    first, second = draft(finance), draft(finance, "90", "90")
    results = race(
        r.user.pk,
        *[
            lambda req, journal=j: (
                posting.post_draft(req, journal.pk, "competing-content-key")[0].pk
            )
            for j in (first, second)
        ],
    )
    assert sum(ok for ok, _ in results) == 1
    assert JournalEntry.objects.filter(status="posted").count() == 1


def test_same_domain_source_with_different_keys_posts_once(finance):
    r, a = finance
    args = dict(
        source_type="test_adapter",
        source_id="one-source",
        source_action="post",
        posting_date=DAY,
        description="One domain operation",
        lines=[
            {"account_id": a["1010"].pk, "debit": "10"},
            {"account_id": a["3010"].pk, "credit": "10"},
        ],
    )
    results = race(
        r.user.pk,
        *[
            lambda req, key=k: posting.post_journal(actor=req.user, posting_key=key, **args).pk
            for k in ("source-client-key-a", "source-client-key-b")
        ],
    )
    assert all(ok for ok, _ in results)
    assert results[0][1] == results[1][1]
    assert JournalEntry.objects.filter(status="posted").count() == 1


def test_duplicate_reversals_have_one_result(finance):
    r, _ = finance
    original = post(finance)
    results = race(
        r.user.pk,
        *[
            lambda req, k=key: posting.reverse(req, original.pk, DAY, "Correct original", k).pk
            for key in ("reversal-concurrent-a", "reversal-concurrent-b")
        ],
    )
    assert all(ok for ok, _ in results)
    assert results[0][1] == results[1][1]
    assert JournalEntry.objects.filter(reversal_of=original, status="posted").count() == 1


def test_posting_and_period_close_serialize(finance):
    r, _ = finance
    journal = draft(finance)
    period = AccountingPeriod.objects.get(start=date(2026, 10, 1))
    results = race(
        r.user.pk,
        lambda req: posting.post_draft(req, journal.pk, "posting-during-close")[0].pk,
        lambda req: setup.set_period(req, period.pk, True).pk,
    )
    assert results[1][0]
    journal.refresh_from_db()
    period.refresh_from_db()
    assert period.is_closed
    assert journal.status == ("posted" if results[0][0] else "draft")
    if not results[0][0]:
        assert "open accounting period" in str(results[0][1])


def test_first_posting_and_base_currency_change_serialize(finance):
    r, _ = finance
    journal = draft(finance)
    results = race(
        r.user.pk,
        lambda req: posting.post_draft(req, journal.pk, "first-post-settings-race")[0].pk,
        lambda req: update_company(req, {"base_currency": "USD"}).pk,
    )
    assert sum(ok for ok, _ in results) == 1
    journal.refresh_from_db()
    company = CompanyProfile.objects.get(pk=1)
    assert (journal.status, company.base_currency) in (("posted", "BDT"), ("draft", "USD"))


def test_concurrent_parent_changes_cannot_create_cycle(finance):
    r, _ = finance
    a = setup.save_account(
        r, {"code": "1200", "name": "Group A", "account_type": "asset", "is_postable": False}
    )
    b = setup.save_account(
        r, {"code": "1300", "name": "Group B", "account_type": "asset", "is_postable": False}
    )
    results = race(
        r.user.pk,
        lambda req: setup.save_account(req, {"parent_id": b.pk}, a.pk).pk,
        lambda req: setup.save_account(req, {"parent_id": a.pk}, b.pk).pk,
    )
    assert sum(ok for ok, _ in results) == 1
    assert not (
        Account.objects.get(pk=a.pk).parent_id == b.pk
        and Account.objects.get(pk=b.pk).parent_id == a.pk
    )
