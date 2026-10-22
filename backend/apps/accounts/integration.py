"""Scoped, revocable, high-entropy credentials for the dedicated AIA identity."""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.accounts.authorization import get_permission_codes
from apps.accounts.models import IntegrationToken, User
from apps.audit.services import record

IDENTITY = "assistant"
EMAIL = "assistant@netamate.com"
ROLE = "ai_assistant_integration"
DEFAULT_SCOPES = frozenset(
    {
        "company.read",
        "customers.read",
        "customers.write",
        "vendors.read",
        "vendors.write",
        "invoices.read",
        "invoices.draft",
        "documents.read",
        "reporting.read",
    }
)
# Token access is never equal to the role's full powers: all requests must
# match one exact allowlisted endpoint + method + token scope.
POLICIES = (
    (re.compile(r"^/api/v1/company/summary/$"), {"GET": "company.read"}),
    (
        re.compile(r"^/api/v1/sales/customers/(?:[0-9]+/)?$"),
        {
            "GET": "customers.read",
            "POST": "customers.write",
            "PATCH": "customers.write",
            "PUT": "customers.write",
        },
    ),
    (
        re.compile(r"^/api/v1/purchasing/vendors/(?:[0-9]+/)?$"),
        {
            "GET": "vendors.read",
            "POST": "vendors.write",
            "PATCH": "vendors.write",
            "PUT": "vendors.write",
        },
    ),
    (
        re.compile(r"^/api/v1/billing/invoices/(?:[0-9]+/)?$"),
        {
            "GET": "invoices.read",
            "POST": "invoices.draft",
            "PATCH": "invoices.draft",
            "PUT": "invoices.draft",
        },
    ),
    (re.compile(r"^/api/v1/documents/(?:[0-9]+/)?$"), {"GET": "documents.read"}),
    (re.compile(r"^/api/v1/reporting/dashboard/$"), {"GET": "reporting.read"}),
    (re.compile(r"^/api/v1/reporting/search/$"), {"GET": "reporting.read"}),
)
REQUIRED_ROLE_PERMISSION = {
    "company.read": "company.view",
    "customers.read": "finance.view",
    "customers.write": "sales.manage",
    "vendors.read": "finance.view",
    "vendors.write": "vendors.manage",
    "invoices.read": "finance.view",
    "invoices.draft": "invoices.create",
    "documents.read": "documents.client.view",
    "reporting.read": "finance.view",
}
_TOKEN_SHAPE = re.compile(r"^aia_([a-f0-9]{16})_([A-Za-z0-9_-]{40,100})$")


def allowed_scope(method: str, path: str):
    for pattern, methods in POLICIES:
        if pattern.fullmatch(path):
            # No GET/POST authorization inheritance for HEAD, OPTIONS,
            # DELETE, PUT of unsupported resources or arbitrary subactions.
            return methods.get(method)
    return None


@transaction.atomic
def issue_token(*, name: str, days: int, scopes: set[str]) -> str:
    if not 1 <= days <= 90:
        raise ValueError("Token lifetime must be between 1 and 90 days.")
    if not name or len(name) > 80:
        raise ValueError("Token name must be 1-80 characters.")
    if not scopes or not scopes <= DEFAULT_SCOPES:
        raise ValueError("Request only approved AIA scopes.")
    user = User.objects.select_related("role").get(username=IDENTITY, email=EMAIL)
    if not user.is_active or not user.role or user.role.key != ROLE:
        raise ValueError("AIA identity is not active or has an unexpected role.")
    if user.has_usable_password():
        raise ValueError("AIA account must have password login disabled.")
    actual = get_permission_codes(user)
    if any(REQUIRED_ROLE_PERMISSION[scope] not in actual for scope in scopes):
        raise ValueError("AIA role does not hold all requested scope permissions.")
    prefix = secrets.token_hex(8)
    secret = secrets.token_urlsafe(36)
    plaintext = f"aia_{prefix}_{secret}"
    row = IntegrationToken.objects.create(
        user=user,
        name=name,
        prefix=prefix,
        token_hash=hashlib.sha256(plaintext.encode("ascii")).hexdigest(),
        scopes=sorted(scopes),
        expires_at=timezone.now() + timedelta(days=days),
    )
    record(
        "integration.token_issued",
        target=row,
        after={
            "name": name,
            "prefix": prefix,
            "scopes": sorted(scopes),
            "expires_at": row.expires_at.isoformat(),
        },
        reason="Created by authorized server-side operator, never logged in plaintext.",
    )
    return plaintext


@transaction.atomic
def revoke_token(prefix: str) -> bool:
    row = IntegrationToken.objects.select_for_update().get(prefix=prefix)
    if row.revoked_at:
        return False
    row.revoked_at = timezone.now()
    row.save(update_fields=["revoked_at"])
    record(
        "integration.token_revoked",
        target=row,
        after={"name": row.name, "prefix": row.prefix},
        reason="Revoked by authorized server-side operator.",
    )
    return True


def authenticate_token(value: str, method: str, path: str):
    match = _TOKEN_SHAPE.fullmatch(value)
    if not match:
        raise AuthenticationFailed("Invalid integration credential.")
    prefix = match.group(1)
    row = IntegrationToken.objects.select_related("user__role").filter(prefix=prefix).first()
    if row is None or not hmac.compare_digest(
        hashlib.sha256(value.encode("ascii")).hexdigest(), row.token_hash
    ):
        raise AuthenticationFailed("Invalid integration credential.")
    if row.revoked_at or row.expires_at <= timezone.now():
        raise AuthenticationFailed("Integration credential expired or revoked.")
    user = row.user
    if (
        not user.is_active
        or user.username != IDENTITY
        or user.email != EMAIL
        or not user.role
        or not user.role.is_active
        or user.role.key != ROLE
        or user.has_usable_password()
    ):
        raise AuthenticationFailed("Integration identity is unavailable.")
    scope = allowed_scope(method, path)
    if not scope or scope not in row.scopes:
        raise PermissionDenied("AIA token does not permit this operation.")
    if REQUIRED_ROLE_PERMISSION[scope] not in get_permission_codes(user):
        raise PermissionDenied("AIA role does not permit this operation.")
    # No token value, request payload or secret material is persisted to audit.
    IntegrationToken.objects.filter(pk=row.pk).update(last_used_at=timezone.now())
    return user, row
