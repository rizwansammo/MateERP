"""Dedicated AIA bearer token: no password, explicit scopes, revocation, CSRF isolation."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.integration import DEFAULT_SCOPES, issue_token, revoke_token
from apps.accounts.models import IntegrationToken, Permission, Role
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def aia(make_user):
    role = Role.objects.create(key="ai_assistant_integration", name="AI Assistant Integration")
    role.permissions.set(
        Permission.objects.filter(
            code__in=[
                "company.view",
                "finance.view",
                "sales.manage",
                "invoices.create",
                "vendors.manage",
                "documents.client.view",
                "documents.vendor.view",
                "reports.export",
            ]
        )
    )
    user = make_user("assistant", None, email="assistant@netamate.com")
    user.role = role
    user.set_unusable_password()
    user.save()
    return user


def client_with(token):
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_token_is_hashed_and_can_read_allowed_api(aia):
    token = issue_token(name="Test automation", days=30, scopes=set(DEFAULT_SCOPES))
    obj = IntegrationToken.objects.get()
    assert token.startswith(f"aia_{obj.prefix}_")
    assert token not in obj.token_hash
    assert len(obj.token_hash) == 64
    assert obj.expires_at > timezone.now()
    assert AuditEvent.objects.filter(action="integration.token_issued").exists()

    response = client_with(token).get("/api/v1/reporting/search/?q=example")
    assert response.status_code == 200, response.data
    obj.refresh_from_db()
    assert obj.last_used_at is not None


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/users/", "get"),
        ("/api/v1/roles/", "get"),
        ("/api/v1/auth/me/", "get"),
        ("/api/v1/purchasing/expenses/", "post"),
        ("/api/v1/billing/invoices/1/issue/", "post"),
        ("/api/v1/sales/customers/1/", "delete"),
        ("/api/v1/accounts/", "get"),
    ],
)
def test_forbidden_routes_fail_closed(aia, path, method):
    token = issue_token(name="Restricted", days=30, scopes=set(DEFAULT_SCOPES))
    client = client_with(token)
    response = getattr(client, method)(path, {}, format="json")
    assert response.status_code == 403, (path, response.data)


def test_bearer_scope_limits_writes_and_allows_read(aia):
    token = issue_token(name="Read-only", days=7, scopes={"customers.read"})
    client = client_with(token)
    assert client.get("/api/v1/sales/customers/").status_code == 200
    assert (
        client.post(
            "/api/v1/sales/customers/", {"name": "Never created"}, format="json"
        ).status_code
        == 403
    )
    assert client.get("/api/v1/purchasing/vendors/").status_code == 403


def test_invalid_revoked_expired_role_disabled_and_password_blocked(aia):
    token = issue_token(name="Lifecycle", days=7, scopes={"customers.read"})
    client = client_with(token)
    path = "/api/v1/sales/customers/"
    assert client.get(path).status_code == 200
    assert client_with(token[:-1] + "!").get(path).status_code == 401
    assert revoke_token(IntegrationToken.objects.get().prefix) is True
    assert client.get(path).status_code == 401
    assert revoke_token(IntegrationToken.objects.get().prefix) is False
    assert AuditEvent.objects.filter(action="integration.token_revoked").exists()
    obj = IntegrationToken.objects.get()
    obj.revoked_at = None
    obj.expires_at = timezone.now() - timedelta(seconds=1)
    obj.save()
    assert client.get(path).status_code == 401
    obj.expires_at = timezone.now() + timedelta(days=2)
    obj.save()
    aia.role.is_active = False
    aia.role.save()
    assert client.get(path).status_code == 401
    aia.role.is_active = True
    aia.role.save()
    aia.set_password("UnwantedLogin2026!")
    aia.save()
    assert client.get(path).status_code == 401


def test_issuance_checks_identity_role_scope_and_ttl(aia):
    with pytest.raises(ValueError, match="between 1 and 90"):
        issue_token(name="Bad", days=91, scopes={"customers.read"})
    with pytest.raises(ValueError, match="approved"):
        issue_token(name="Bad", days=1, scopes={"users.manage"})
    aia.role.permissions.remove(Permission.objects.get(code="sales.manage"))
    with pytest.raises(ValueError, match="does not hold"):
        issue_token(name="Bad", days=1, scopes={"customers.write"})


def test_session_authentication_still_behaves_normally(aia, admin_client):
    assert admin_client.get("/api/v1/auth/me/").status_code == 200
    assert admin_client.get("/api/v1/users/").status_code == 200
    assert APIClient().get("/api/v1/users/").status_code == 401


def test_authorized_aia_can_insert_customer_using_api(aia, company):
    token = issue_token(
        name="Create customer",
        days=1,
        scopes={"customers.write", "customers.read"},
    )
    client = client_with(token)
    response = client.post(
        "/api/v1/sales/customers/",
        {"name": "AI-created Customer", "currency": "BDT"},
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["name"] == "AI-created Customer"
    record_id = response.data["id"]
    assert client.get(f"/api/v1/sales/customers/{record_id}/").status_code == 200
    assert client.delete(f"/api/v1/sales/customers/{record_id}/").status_code == 403
