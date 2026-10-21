from datetime import date
from types import SimpleNamespace

import pytest

from apps.accounting.services.setup import save_account
from apps.banking.services import save_account as save_bank
from apps.company.models import FinancialParty


@pytest.fixture
def founder_books(books, make_user):
    reviewer = make_user("founder-reviewer", "administrator")
    admin = books.request
    bank = save_bank(
        admin,
        {
            "name": "Founder company bank",
            "kind": "bank",
            "currency": "BDT",
            "gl_account_id": books.accounts["1020"].pk,
        },
    )
    for index, purpose in enumerate(
        (
            "founder_payable",
            "founder_loan",
            "founder_pending",
            "founder_equity",
            "share_capital",
            "share_premium",
        )
    ):
        liability = index < 3
        save_account(
            admin,
            {
                "code": f"F{index}",
                "name": purpose,
                "account_type": "liability" if liability else "equity",
                "parent_id": books.accounts["2000" if liability else "3000"].pk,
                "control": purpose,
            },
        )
    a = FinancialParty.objects.create(
        name="Founder A",
        kind="individual",
        joined=date(2026, 1, 1),
        is_founder=True,
        is_shareholder=True,
        user=admin.user,
    )
    b = FinancialParty.objects.create(
        name="Founder B",
        kind="individual",
        joined=date(2026, 1, 1),
        is_founder=True,
        is_shareholder=True,
        user=reviewer,
    )
    return SimpleNamespace(
        **vars(books), reviewer=SimpleNamespace(user=reviewer, META={}), bank=bank, a=a, b=b
    )
