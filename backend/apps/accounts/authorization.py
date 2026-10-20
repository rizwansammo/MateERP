"""Server-side permission evaluation.

Permissions are always read from the database for the current request, so
role and permission changes apply to every user immediately — there is no
cached privilege in sessions or on the client.
"""

from rest_framework import exceptions
from rest_framework.permissions import BasePermission

from .catalog import ALL_CODES

_CACHE_ATTR = "_mateerp_permission_codes"


def get_permission_codes(user) -> frozenset[str]:
    """Effective permission codes for ``user`` (empty when inactive or role-less)."""
    if user is None or not user.is_authenticated or not user.is_active:
        return frozenset()
    cached = getattr(user, _CACHE_ATTR, None)
    if cached is not None:
        return cached
    role = user.role
    if role is None or not role.is_active:
        codes: frozenset[str] = frozenset()
    elif role.is_admin:
        codes = ALL_CODES
    else:
        codes = frozenset(role.permissions.values_list("code", flat=True))
    setattr(user, _CACHE_ATTR, codes)
    return codes


def clear_permission_cache(user) -> None:
    if hasattr(user, _CACHE_ATTR):
        delattr(user, _CACHE_ATTR)


def has_perm(user, code: str) -> bool:
    return code in get_permission_codes(user)


def is_administrator(user) -> bool:
    return bool(
        user is not None
        and user.is_authenticated
        and user.is_active
        and user.role
        and user.role.is_admin
    )


def require(user, *codes: str) -> None:
    """Raise PermissionDenied unless ``user`` holds all ``codes``."""
    held = get_permission_codes(user)
    if not set(codes) <= held:
        raise exceptions.PermissionDenied()


class PasswordChangeRequired(exceptions.PermissionDenied):
    default_detail = "You must change your password before continuing."
    default_code = "password_change_required"


class IsActiveUser(BasePermission):
    """Default permission: an authenticated, active user with no pending forced password change.

    Views that must stay reachable during a forced change (session, profile,
    password change, logout) set ``allow_password_change_required = True``.
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if user.must_change_password and not getattr(view, "allow_password_change_required", False):
            raise PasswordChangeRequired()
        return True


class HasPermissions(BasePermission):
    """Base for ``requires(...)``; ``codes`` must all be held."""

    codes: tuple[str, ...] = ()

    def has_permission(self, request, view) -> bool:
        return set(self.codes) <= get_permission_codes(request.user)


class HasAnyPermission(BasePermission):
    codes: tuple[str, ...] = ()

    def has_permission(self, request, view) -> bool:
        return bool(set(self.codes) & get_permission_codes(request.user))


def requires_any(*codes: str) -> type[HasAnyPermission]:
    """DRF permission class requiring at least one of the given codes."""
    unknown = set(codes) - ALL_CODES
    if unknown:
        raise ValueError(f"Unknown permission codes: {sorted(unknown)}")
    return type(f"RequiresAny[{','.join(codes)}]", (HasAnyPermission,), {"codes": tuple(codes)})


def requires(*codes: str) -> type[HasPermissions]:
    """DRF permission class requiring every given permission code."""
    unknown = set(codes) - ALL_CODES
    if unknown:
        raise ValueError(f"Unknown permission codes: {sorted(unknown)}")
    return type(f"Requires[{','.join(codes)}]", (HasPermissions,), {"codes": tuple(codes)})
