from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from django.db import close_old_connections, connections

from apps.accounts.models import User
from apps.core.exceptions import BusinessRuleViolation
from apps.founders.models import CorporateTransaction
from apps.founders.services import corporate

from .test_corporate import expense, receipt

pytestmark = pytest.mark.django_db(transaction=True)


def test_concurrent_verification_posts_a_source_once(founder_books):
    f = founder_books
    source = corporate.record_transaction(
        f.request,
        {
            "kind": "receipt",
            "classification": "pending",
            "party_id": f.a.pk,
            "date": "2026-02-01",
            "currency": "BDT",
            "amount": "20000",
            "bank_id": f.bank.pk,
        },
        "race-one-receipt",
    )

    def worker():
        close_old_connections()
        try:
            request = SimpleNamespace(user=User.objects.get(pk=f.reviewer.user.pk), META={})
            return corporate.verify(request, source.pk, {}).journal_id
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert results[0] == results[1]
    assert CorporateTransaction.objects.get(pk=source.pk).journal_id == results[0]


def test_competing_partial_reimbursements_cannot_overpay(founder_books):
    f = founder_books
    receipt(f, "40000")
    source = expense(f)
    pending = [
        corporate.record_transaction(
            f.request,
            {
                "kind": "reimbursement",
                "classification": "payable",
                "party_id": f.a.pk,
                "date": "2026-02-02",
                "currency": "BDT",
                "amount": "15000",
                "bank_id": f.bank.pk,
                "allocations": [{"obligation_id": source.obligation.pk, "amount": "15000"}],
            },
            f"race-reimburse-{i}",
        )
        for i in range(2)
    ]

    def worker(pk):
        close_old_connections()
        try:
            request = SimpleNamespace(user=User.objects.get(pk=f.reviewer.user.pk), META={})
            try:
                corporate.verify(request, pk, {})
                return "posted"
            except BusinessRuleViolation:
                return "blocked"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, [p.pk for p in pending]))
    assert sorted(results) == ["blocked", "posted"]
    assert corporate.outstanding(source.obligation)[0] == 5000
