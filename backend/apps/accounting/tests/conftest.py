from datetime import date
from types import SimpleNamespace

import pytest

from apps.accounting.services.setup import create_year, setup_chart


@pytest.fixture
def finance(admin_user, company):
    request = SimpleNamespace(user=admin_user, META={})
    accounts = {a.code: a for a in setup_chart(request)}
    create_year(request, date(2026, 1, 1))
    return request, accounts
