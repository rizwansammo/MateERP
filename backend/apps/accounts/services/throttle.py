"""Sign-in abuse protection with sliding windows over ``LoginFailure`` rows.

Three independent limits (all durations in seconds):

* identifier + IP pair — progressive backoff after PAIR_THRESHOLD failures in
  PAIR_WINDOW: 60s, 120s, 240s … capped at PAIR_MAX_DELAY. Someone guessing
  from another address cannot lock the real user out of their own address.
* identifier across all IPs — beyond IDENT_THRESHOLD failures in IDENT_WINDOW,
  attempts for that identifier are only *spaced* IDENT_MIN_INTERVAL apart.
  It never hard-locks, so a distributed attacker cannot deny an
  administrator access indefinitely.
* IP across all identifiers — IP_THRESHOLD failures in IP_WINDOW blocks the
  address for IP_BLOCK (credential stuffing).

Unknown identifiers are throttled exactly like real ones, so throttling never
reveals whether an account exists. Locks expire on their own; operators can
clear them with ``manage.py clear_login_locks``.
"""

from datetime import timedelta

from django.db import connection
from django.db.models import Count, Max
from django.utils import timezone

from apps.accounts.models import LoginFailure

PAIR_THRESHOLD = 5
PAIR_WINDOW = 15 * 60
PAIR_BASE_DELAY = 60
PAIR_MAX_DELAY = 15 * 60

IDENT_THRESHOLD = 20
IDENT_WINDOW = 60 * 60
IDENT_MIN_INTERVAL = 30

IP_THRESHOLD = 50
IP_WINDOW = 15 * 60
IP_BLOCK = 15 * 60

RETENTION = 24 * 60 * 60


def normalise_identifier(identifier: str) -> str:
    return identifier.strip().lower()[:254]


def lock(identifier: str) -> None:
    """Serialise concurrent attempts for one identifier (inside a transaction)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"login:{identifier}"])


def _stats(**filters) -> tuple[int, object]:
    row = LoginFailure.objects.filter(**filters).aggregate(n=Count("id"), last=Max("created_at"))
    return row["n"], row["last"]


def retry_after(identifier: str, ip: str | None) -> int:
    """Seconds the caller must wait before another attempt (0 = allowed)."""
    now = timezone.now()
    waits: list[float] = []

    n, last = _stats(
        identifier=identifier, ip_address=ip, created_at__gte=now - timedelta(seconds=PAIR_WINDOW)
    )
    if n >= PAIR_THRESHOLD and last is not None:
        delay = min(PAIR_BASE_DELAY * 2 ** (n - PAIR_THRESHOLD), PAIR_MAX_DELAY)
        waits.append((last + timedelta(seconds=delay) - now).total_seconds())

    n, last = _stats(identifier=identifier, created_at__gte=now - timedelta(seconds=IDENT_WINDOW))
    if n >= IDENT_THRESHOLD and last is not None:
        waits.append((last + timedelta(seconds=IDENT_MIN_INTERVAL) - now).total_seconds())

    if ip:
        n, last = _stats(ip_address=ip, created_at__gte=now - timedelta(seconds=IP_WINDOW))
        if n >= IP_THRESHOLD and last is not None:
            waits.append((last + timedelta(seconds=IP_BLOCK) - now).total_seconds())

    longest = max(waits, default=0)
    return max(0, int(longest + 0.999))


def record_failure(identifier: str, ip: str | None) -> None:
    LoginFailure.objects.create(identifier=identifier, ip_address=ip)
    LoginFailure.objects.filter(
        created_at__lt=timezone.now() - timedelta(seconds=RETENTION)
    ).delete()


def clear_pair(identifier: str, ip: str | None) -> None:
    LoginFailure.objects.filter(identifier=identifier, ip_address=ip).delete()


def clear(identifier: str | None = None, ip: str | None = None) -> int:
    """Remove recorded failures (all when no filter is given). Returns rows removed."""
    qs = LoginFailure.objects.all()
    if identifier:
        qs = qs.filter(identifier=normalise_identifier(identifier))
    if ip:
        qs = qs.filter(ip_address=ip)
    deleted, _ = qs.delete()
    return deleted


def clear_for_user(user) -> None:
    identifiers = [normalise_identifier(user.username)]
    if user.email:
        identifiers.append(normalise_identifier(user.email))
    LoginFailure.objects.filter(identifier__in=identifiers).delete()
