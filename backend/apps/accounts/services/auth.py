"""Sign-in, sign-out, password and profile services."""

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpRequest
from rest_framework import exceptions

from apps.accounts.models import User
from apps.accounts.services import throttle
from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.core.net import client_ip


class InvalidCredentials(exceptions.AuthenticationFailed):
    default_detail = "The username or password is incorrect."
    default_code = "invalid_credentials"


class TooManyAttempts(exceptions.Throttled):
    default_code = "too_many_attempts"

    def __init__(self, wait: int):
        super().__init__(
            wait=wait,
            detail=f"Too many sign-in attempts. Try again in {wait} seconds.",
        )


def _find_account(identifier: str) -> User | None:
    """The single account an identifier refers to, for audit attribution only."""
    from django.db.models import Q

    query = Q(username__iexact=identifier)
    if "@" in identifier:
        query |= Q(email__iexact=identifier)
    matches = list(User.objects.filter(query)[:2])
    return matches[0] if len(matches) == 1 else None


def sign_in(request: HttpRequest, *, identifier: str, password: str, remember: bool) -> User:
    """Authenticate and start a session, enforcing abuse throttling.

    Failures are recorded *before* the error is raised (in their own
    committed transaction) so throttling cannot be bypassed by the
    rollback of a failed request.
    """
    key = throttle.normalise_identifier(identifier)
    ip = client_ip(request)

    with transaction.atomic():
        throttle.lock(key)
        wait = throttle.retry_after(key, ip)
        if wait:
            account = _find_account(identifier)
            record(
                "auth.login.throttled",
                request=request,
                actor=None,
                target=account,
                target_label="" if account else "unknown identifier",
                outcome=AuditEvent.Outcome.DENIED,
                reason=f"Retry after {wait}s",
            )
        else:
            user = authenticate(request, username=identifier, password=password)
            if user is None:
                throttle.record_failure(key, ip)
                account = _find_account(identifier)
                # Never store the raw identifier for unknown accounts: users
                # sometimes type a password into the username field.
                record(
                    "auth.login.failed",
                    request=request,
                    actor=None,
                    target=account,
                    target_label="" if account else "unknown identifier",
                    outcome=AuditEvent.Outcome.FAILURE,
                )
            else:
                throttle.clear_pair(key, ip)

    if wait:
        raise TooManyAttempts(wait)
    if user is None:
        raise InvalidCredentials()

    login(request, user)  # rotates the session key
    request.session.set_expiry(settings.SESSION_REMEMBER_AGE if remember else 0)
    record(
        "auth.login.succeeded",
        request=request,
        actor=user,
        target=user,
        after={"remember": remember},
    )
    return user


def sign_out(request: HttpRequest) -> None:
    user = request.user if request.user.is_authenticated else None
    if user is not None:
        record("auth.logout", request=request, actor=user, target=user)
    logout(request)  # flushes the server-side session


def change_password(request: HttpRequest, *, current_password: str, new_password: str) -> None:
    user: User = request.user
    if not user.check_password(current_password):
        record(
            "auth.password.change_failed",
            request=request,
            target=user,
            outcome=AuditEvent.Outcome.FAILURE,
            reason="Current password incorrect",
        )
        raise exceptions.ValidationError(
            {"current_password": ["Your current password is incorrect."]}
        )
    if current_password == new_password:
        raise exceptions.ValidationError(
            {"new_password": ["Choose a password different from your current one."]}
        )
    try:
        validate_password(new_password, user)
    except DjangoValidationError as exc:
        raise exceptions.ValidationError({"new_password": list(exc.messages)}) from exc

    with transaction.atomic():
        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        record("auth.password.changed", request=request, target=user)
    # Keep this session (with a fresh key); every other session for the user
    # becomes invalid because the password hash changed.
    update_session_auth_hash(request, user)
    request.session.cycle_key()
