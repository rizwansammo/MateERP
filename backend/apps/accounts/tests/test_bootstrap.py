from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

SECRET = "Initial-Admin-Passphrase-42"


def run(monkeypatch, password=SECRET, **options):
    monkeypatch.setenv("MATEERP_ADMIN_PASSWORD", password)
    out = StringIO()
    call_command("create_admin", no_input=True, stdout=out, **options)
    return out.getvalue()


def test_creates_first_administrator(monkeypatch):
    output = run(monkeypatch, username="owner", email="owner@example.test")
    user = User.objects.get(username="owner")
    assert user.role.is_admin and user.is_active and user.check_password(SECRET)
    assert not user.must_change_password
    assert SECRET not in output
    assert AuditEvent.objects.filter(action="user.admin_bootstrapped").exists()


def test_refuses_when_an_administrator_exists(monkeypatch, admin_user):
    with pytest.raises(CommandError, match="already exists"):
        run(monkeypatch, username="owner", email="owner@example.test")
    run(monkeypatch, username="owner", email="owner@example.test", force_additional=True)
    assert User.objects.filter(role__is_admin=True).count() == 2


def test_rejects_weak_password(monkeypatch):
    with pytest.raises(CommandError, match="Password rejected"):
        run(monkeypatch, password="password", username="owner", email="owner@example.test")
    assert not User.objects.exists()


def test_requires_password_source_without_tty(monkeypatch):
    monkeypatch.delenv("MATEERP_ADMIN_PASSWORD", raising=False)
    with pytest.raises(CommandError, match="MATEERP_ADMIN_PASSWORD"):
        call_command("create_admin", no_input=True, username="owner", email="o@example.test")
