"""Role and permission administration."""

import uuid

from django.db import transaction
from django.http import HttpRequest
from django.utils.text import slugify
from rest_framework import exceptions

from apps.accounts.authorization import get_permission_codes, require
from apps.accounts.catalog import ALL_CODES
from apps.accounts.models import Permission, Role, User
from apps.audit.services import record
from apps.core.exceptions import BusinessRuleViolation


def _assert_grantable(actor: User, codes: set[str]) -> None:
    unknown = codes - ALL_CODES
    if unknown:
        raise exceptions.ValidationError(
            {"permissions": [f"Unknown permissions: {sorted(unknown)}"]}
        )
    missing = codes - get_permission_codes(actor)
    if missing:
        raise exceptions.PermissionDenied(
            "You cannot grant permissions you do not hold: " + ", ".join(sorted(missing))
        )


def _check_name(name: str, exclude_pk=None) -> None:
    qs = Role.objects.filter(name__iexact=name)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise exceptions.ValidationError({"name": ["A role with this name already exists."]})


def _codes(role: Role) -> list[str]:
    return sorted(role.permissions.values_list("code", flat=True))


@transaction.atomic
def create_role(
    request: HttpRequest, *, name: str, description: str, permissions: set[str]
) -> Role:
    actor: User = request.user
    _check_name(name)
    if permissions:
        require(actor, "permissions.manage")
        _assert_grantable(actor, permissions)
    role = Role.objects.create(
        key=f"{slugify(name)[:40] or 'role'}-{uuid.uuid4().hex[:8]}",
        name=name,
        description=description,
    )
    role.permissions.set(Permission.objects.filter(code__in=permissions))
    record(
        "role.created",
        request=request,
        target=role,
        after={"name": name, "permissions": sorted(permissions)},
    )
    return role


@transaction.atomic
def update_role(request: HttpRequest, role: Role, *, data: dict) -> Role:
    role = Role.objects.select_for_update().get(pk=role.pk)
    if role.is_admin:
        raise BusinessRuleViolation(
            "The Administrator role cannot be changed.", code="admin_role_locked"
        )
    before = {"name": role.name, "description": role.description, "is_active": role.is_active}

    if "name" in data and data["name"] != role.name:
        if role.is_system:
            raise BusinessRuleViolation("Default roles cannot be renamed.", code="system_role")
        _check_name(data["name"], exclude_pk=role.pk)
        role.name = data["name"]
    if "description" in data:
        role.description = data["description"]
    if "is_active" in data and data["is_active"] != role.is_active:
        if not data["is_active"] and role.users.filter(is_active=True).exists():
            raise BusinessRuleViolation(
                "Reassign this role's active users before deactivating it.", code="role_in_use"
            )
        role.is_active = data["is_active"]
    role.save()

    after = {"name": role.name, "description": role.description, "is_active": role.is_active}
    if before != after:
        record("role.updated", request=request, target=role, before=before, after=after)
    return role


@transaction.atomic
def set_role_permissions(request: HttpRequest, changes: dict[int, set[str]]) -> list[Role]:
    """Replace the permission sets of several roles atomically (permission matrix save)."""
    actor: User = request.user
    roles = {r.pk: r for r in Role.objects.select_for_update().filter(pk__in=changes.keys())}
    missing = set(changes) - set(roles)
    if missing:
        raise exceptions.ValidationError({"roles": [f"Unknown roles: {sorted(missing)}"]})

    updated: list[Role] = []
    for pk, codes in changes.items():
        role = roles[pk]
        if role.is_admin:
            raise BusinessRuleViolation(
                "Administrator permissions are fixed.", code="admin_role_locked"
            )
        before = set(_codes(role))
        # Granting needs the permission; revoking anything you could not grant
        # is equally an escalation path for others, so both directions apply.
        _assert_grantable(actor, (codes - before) | (before - codes))
        if codes == before:
            continue
        role.permissions.set(Permission.objects.filter(code__in=codes))
        record(
            "role.permissions_changed",
            request=request,
            target=role,
            before={"permissions": sorted(before)},
            after={"permissions": sorted(codes)},
        )
        updated.append(role)
    return updated
