"""User administration: creation, updates, activation and credential resets."""

import secrets
import string

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.http import HttpRequest
from rest_framework import exceptions

from apps.accounts.authorization import get_permission_codes, is_administrator
from apps.accounts.models import Role, User
from apps.accounts.services import throttle
from apps.audit.services import diff, record
from apps.core.exceptions import BusinessRuleViolation

_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "Il1O0o")


def generate_temporary_password(length: int = 16) -> str:
    """A strong one-time password containing upper, lower and digits."""
    while True:
        candidate = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
        ):
            return candidate


def role_permission_codes(role: Role) -> frozenset[str]:
    from apps.accounts.catalog import ALL_CODES

    if role.is_admin:
        return ALL_CODES
    return frozenset(role.permissions.values_list("code", flat=True))


def assert_can_assign_role(actor: User, role: Role) -> None:
    """Anti-escalation: an actor may only hand out access they hold themselves."""
    if not role.is_active:
        raise exceptions.ValidationError({"role": ["This role is inactive."]})
    if role.is_admin and not is_administrator(actor):
        raise exceptions.PermissionDenied("Only administrators can assign the Administrator role.")
    if not role_permission_codes(role) <= get_permission_codes(actor):
        raise exceptions.PermissionDenied(
            "You cannot assign a role with permissions you do not hold."
        )


def assert_can_manage_user(actor: User, user: User) -> None:
    """Actors may only manage users whose access they fully hold themselves."""
    if user.pk == actor.pk or user.role is None:
        return
    if not role_permission_codes(user.role) <= get_permission_codes(actor):
        raise exceptions.PermissionDenied("You cannot manage a user who has more access than you.")


def _lock_active_admins() -> list[int]:
    """Lock and return ids of active administrators (serialises last-admin checks)."""
    return list(
        User.objects.select_for_update()
        .filter(is_active=True, role__is_admin=True)
        .values_list("id", flat=True)
    )


def assert_not_last_admin(user: User) -> None:
    admins = _lock_active_admins()
    if user.pk in admins and len(admins) <= 1:
        raise BusinessRuleViolation(
            "This is the last active administrator. Assign the Administrator role to another "
            "active user first.",
            code="last_administrator",
        )


def _snapshot(user: User) -> dict:
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "role": user.role.name if user.role else None,
        "is_active": user.is_active,
    }


def _check_unique(username: str | None, email: str | None, exclude_pk=None) -> None:
    errors: dict[str, list[str]] = {}
    qs = User.objects.exclude(pk=exclude_pk) if exclude_pk else User.objects.all()
    if username and qs.filter(username__iexact=username).exists():
        errors["username"] = ["This username is already taken."]
    if email and qs.filter(email__iexact=email).exists():
        errors["email"] = ["Another user already uses this email address."]
    if errors:
        raise exceptions.ValidationError(errors)


@transaction.atomic
def create_user(
    request: HttpRequest,
    *,
    username: str,
    email: str,
    first_name: str,
    last_name: str,
    role: Role,
    is_active: bool = True,
) -> tuple[User, str]:
    """Create a user with a one-time temporary password (returned once, never stored)."""
    actor: User = request.user
    _check_unique(username, email)
    assert_can_assign_role(actor, role)

    temporary_password = generate_temporary_password()
    user = User(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_active=is_active,
        must_change_password=True,
    )
    validate_password(temporary_password, user)
    user.set_password(temporary_password)
    user.save()
    record("user.created", request=request, target=user, after=_snapshot(user))
    return user, temporary_password


@transaction.atomic
def update_user(request: HttpRequest, user: User, *, data: dict) -> User:
    actor: User = request.user
    user = User.objects.select_for_update().get(pk=user.pk)
    assert_can_manage_user(actor, user)
    before = _snapshot(user)

    _check_unique(None, data.get("email"), exclude_pk=user.pk)
    for field in ("first_name", "last_name", "email"):
        if field in data:
            setattr(user, field, data[field])

    new_role: Role | None = data.get("role")
    if new_role is not None and new_role.pk != user.role_id:
        if user.pk == actor.pk:
            raise exceptions.PermissionDenied("You cannot change your own role.")
        assert_can_assign_role(actor, new_role)
        if user.role and user.role.is_admin and not new_role.is_admin:
            assert_not_last_admin(user)
        user.role = new_role

    user.save()
    old, new = diff(before, _snapshot(user))
    if old != new:
        record("user.updated", request=request, target=user, before=old, after=new)
        if "role" in new:
            record(
                "user.role_changed",
                request=request,
                target=user,
                before={"role": old["role"]},
                after={"role": new["role"]},
            )
    return user


@transaction.atomic
def set_active(request: HttpRequest, user: User, *, active: bool) -> User:
    actor: User = request.user
    user = User.objects.select_for_update().get(pk=user.pk)
    if user.is_active == active:
        return user
    assert_can_manage_user(actor, user)
    if not active:
        if user.pk == actor.pk:
            raise BusinessRuleViolation(
                "You cannot deactivate your own account.", code="self_deactivation"
            )
        assert_not_last_admin(user)
    user.is_active = active
    user.save(update_fields=["is_active"])
    # Deactivated users can no longer authenticate: Django rejects inactive
    # users when loading the session user, so existing sessions stop working.
    record(
        "user.reactivated" if active else "user.deactivated",
        request=request,
        target=user,
        before={"is_active": not active},
        after={"is_active": active},
    )
    return user


@transaction.atomic
def reset_password(request: HttpRequest, user: User) -> str:
    """Issue a new one-time password; all of the user's sessions end."""
    actor: User = request.user
    if user.pk == actor.pk:
        raise BusinessRuleViolation("Use Change password for your own account.", code="self_reset")
    assert_can_manage_user(actor, user)
    temporary_password = generate_temporary_password()
    user.set_password(temporary_password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])
    throttle.clear_for_user(user)
    record("user.password_reset", request=request, target=user)
    return temporary_password
