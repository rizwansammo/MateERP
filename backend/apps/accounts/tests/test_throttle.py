from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import RequestFactory
from django.utils import timezone

from apps.accounts.models import LoginFailure
from apps.accounts.services import throttle
from apps.core.net import client_ip
from conftest import PASSWORD, csrf_client

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"


def attempt(client, identifier, password="wrong", ip="203.0.113.10"):
    return client.post(
        LOGIN, {"identifier": identifier, "password": password}, format="json", REMOTE_ADDR=ip
    )


def test_pair_backoff_starts_after_five_failures(make_user):
    make_user("alice")
    client = csrf_client()
    for _ in range(5):
        assert attempt(client, "alice").status_code == 401
    blocked = attempt(client, "alice", PASSWORD)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_attempts"
    assert 0 < int(blocked["Retry-After"]) <= 60


def test_backoff_grows_and_is_capped():
    now = timezone.now()
    LoginFailure.objects.bulk_create(
        [LoginFailure(identifier="alice", ip_address="203.0.113.10") for _ in range(12)]
    )
    LoginFailure.objects.update(created_at=now)
    assert throttle.retry_after("alice", "203.0.113.10") == throttle.PAIR_MAX_DELAY


def test_attacker_on_other_ip_cannot_lock_out_real_user(make_user):
    make_user("alice")
    attacker = csrf_client()
    for _ in range(8):
        attempt(attacker, "alice", ip="198.51.100.66")
    assert attempt(attacker, "alice", ip="198.51.100.66").status_code == 429
    # The real user, from their own address, signs in normally.
    assert attempt(csrf_client(), "alice", PASSWORD, ip="203.0.113.10").status_code == 200


def test_distributed_guessing_only_spaces_attempts(make_user):
    make_user("alice")
    now = timezone.now() - timedelta(seconds=60)
    LoginFailure.objects.bulk_create(
        [LoginFailure(identifier="alice", ip_address=f"198.51.100.{i}") for i in range(25)]
    )
    LoginFailure.objects.update(created_at=now)
    # Last failure was 60s ago: the 30s spacing has elapsed, so no hard lock.
    assert throttle.retry_after("alice", "203.0.113.10") == 0
    LoginFailure.objects.create(identifier="alice", ip_address="198.51.100.99")
    assert 0 < throttle.retry_after("alice", "203.0.113.10") <= throttle.IDENT_MIN_INTERVAL


def test_ip_block_for_credential_stuffing():
    LoginFailure.objects.bulk_create(
        [LoginFailure(identifier=f"user{i}", ip_address="198.51.100.7") for i in range(50)]
    )
    assert throttle.retry_after("someone-new", "198.51.100.7") > 0
    assert throttle.retry_after("someone-new", "198.51.100.8") == 0


def test_unknown_and_known_identifiers_are_throttled_identically(make_user):
    make_user("alice")
    client = csrf_client()
    for name in ("alice", "ghost"):
        for _ in range(5):
            attempt(client, name)
        assert attempt(client, name).status_code == 429


def test_successful_login_clears_pair_failures(make_user):
    make_user("alice")
    client = csrf_client()
    for _ in range(3):
        attempt(client, "alice")
    assert attempt(client, "alice", PASSWORD).status_code == 200
    assert not LoginFailure.objects.filter(identifier="alice", ip_address="203.0.113.10").exists()


def test_clear_login_locks_command():
    LoginFailure.objects.create(identifier="alice", ip_address="203.0.113.10")
    LoginFailure.objects.create(identifier="bob", ip_address="203.0.113.11")
    call_command("clear_login_locks", identifier="ALICE")
    assert list(LoginFailure.objects.values_list("identifier", flat=True)) == ["bob"]


def test_forwarded_for_is_ignored_from_untrusted_peers():
    request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.5", HTTP_X_FORWARDED_FOR="1.2.3.4")
    assert client_ip(request) == "203.0.113.5"


def test_forwarded_for_uses_rightmost_untrusted_hop_from_trusted_proxy():
    # test settings trust 10.99.0.0/16
    request = RequestFactory().get(
        "/", REMOTE_ADDR="10.99.0.1", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9, 10.99.0.2"
    )
    assert client_ip(request) == "203.0.113.9"
