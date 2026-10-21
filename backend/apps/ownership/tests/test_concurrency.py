from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace

import pytest
from django.db import close_old_connections, connections

from apps.accounts.models import User
from apps.core.exceptions import BusinessRuleViolation
from apps.ownership.models import OwnershipProposal
from apps.ownership.services import register

from .test_register import formal_opening

pytestmark = pytest.mark.django_db(transaction=True)


def test_competing_transfer_proposals_cannot_reserve_the_same_holdings(founder_books, make_user):
    f = founder_books
    governor = SimpleNamespace(user=make_user("oversell-reviewer", "administrator"), META={})
    cls = formal_opening(f, governor)

    def worker(index):
        close_old_connections()
        try:
            request = SimpleNamespace(user=User.objects.get(pk=f.request.user.pk), META={})
            try:
                register.propose(
                    request,
                    {
                        "kind": "transfer",
                        "title": "Competing transfer",
                        "effective_date": "2026-03-01",
                        "share_class_id": cls.pk,
                        "rationale": "A reservation cannot oversell",
                        "legal_reference": f"RESERVE-{index}",
                        "lines": [{"transferor_id": f.a.pk, "recipient_id": f.b.pk, "units": 4000}],
                    },
                    f"competing-transfer-{index}",
                )
                return "reserved"
            except BusinessRuleViolation as exc:
                assert exc.get_codes() == "shares_reserved"
                return "blocked"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(worker, range(2)))
    assert sorted(outcomes) == ["blocked", "reserved"]
    assert OwnershipProposal.objects.filter(kind="transfer").count() == 1
    # A reservation is not a confirmed transfer, even when the proposal saved.
    assert register.holdings(date(2026, 3, 1))[str(cls.pk)]["units"][str(f.a.pk)] == 5000
