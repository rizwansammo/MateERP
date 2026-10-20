import pytest

from apps.accounts.catalog import ALL_CODES
from apps.accounts.models import Permission, Role
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

ROLES = "/api/v1/roles/"
MATRIX = "/api/v1/roles/permissions/"


def test_default_roles_and_catalog_exist():
    assert set(Permission.objects.values_list("code", flat=True)) == ALL_CODES
    keys = set(Role.objects.values_list("key", flat=True))
    assert {
        "administrator",
        "finance_manager",
        "accountant",
        "operations_manager",
        "viewer",
    } <= keys
    viewer = Role.objects.get(key="viewer")
    assert list(viewer.permissions.values_list("code", flat=True)) == ["finance.view"]
    assert Role.objects.filter(is_admin=True).count() == 1


def test_role_list_shows_admin_with_all_permissions(admin_client):
    roles = {r["key"]: r for r in admin_client.get(ROLES).json()}
    assert set(roles["administrator"]["permissions"]) == ALL_CODES
    assert roles["administrator"]["user_count"] == 1


def test_create_custom_role_with_permissions(admin_client):
    response = admin_client.post(
        ROLES,
        {"name": "Auditor", "description": "Reads the audit log", "permissions": ["audit.view"]},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["permissions"] == ["audit.view"]
    assert admin_client.post(ROLES, {"name": "auditor"}, format="json").status_code == 400


def test_matrix_change_takes_effect_immediately(admin_client, make_user, client_for):
    accountant = make_user("acc", "accountant")
    client = client_for(accountant)
    assert client.get("/api/v1/branding/").status_code == 200  # via company.view

    role = Role.objects.get(key="accountant")
    codes = sorted(set(role.permissions.values_list("code", flat=True)) - {"company.view"})
    response = admin_client.post(MATRIX, {"changes": {str(role.pk): codes}}, format="json")
    assert response.status_code == 200
    # Same session, no re-login: the privilege is gone at once.
    assert client.get("/api/v1/branding/").status_code == 403
    assert AuditEvent.objects.filter(action="role.permissions_changed").exists()


def test_administrator_role_is_locked(admin_client):
    admin_role = Role.objects.get(is_admin=True)
    response = admin_client.post(MATRIX, {"changes": {str(admin_role.pk): []}}, format="json")
    assert response.status_code == 409
    assert (
        admin_client.patch(
            f"{ROLES}{admin_role.pk}/", {"is_active": False}, format="json"
        ).status_code
        == 409
    )


def test_cannot_grant_permissions_you_do_not_hold(make_user, client_for):
    role = Role.objects.create(key="perm-admin", name="Permission admin")
    role.permissions.set(Permission.objects.filter(code__in=["permissions.manage", "finance.view"]))
    actor = make_user("pa", None)
    actor.role = role
    actor.save()
    viewer = Role.objects.get(key="viewer")
    response = client_for(actor).post(
        MATRIX, {"changes": {str(viewer.pk): ["finance.view", "audit.view"]}}, format="json"
    )
    assert response.status_code == 403
    # Nor can they escalate their own role.
    response = client_for(actor).post(
        MATRIX,
        {"changes": {str(role.pk): ["permissions.manage", "finance.view", "users.manage"]}},
        format="json",
    )
    assert response.status_code == 403


def test_role_in_use_cannot_be_deactivated(admin_client, make_user):
    make_user("v1", "viewer")
    viewer = Role.objects.get(key="viewer")
    response = admin_client.patch(f"{ROLES}{viewer.pk}/", {"is_active": False}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "role_in_use"


def test_system_roles_cannot_be_renamed(admin_client):
    viewer = Role.objects.get(key="viewer")
    response = admin_client.patch(f"{ROLES}{viewer.pk}/", {"name": "Readers"}, format="json")
    assert response.status_code == 409


def test_user_with_inactive_role_has_no_permissions(make_user, client_for, admin_client):
    role = Role.objects.create(key="temp", name="Temp")
    role.permissions.set(Permission.objects.filter(code="audit.view"))
    user = make_user("t", None)
    user.role = role
    user.save()
    client = client_for(user)
    assert client.get("/api/v1/audit/events/").status_code == 200
    Role.objects.filter(pk=role.pk).update(is_active=False)
    assert client.get("/api/v1/audit/events/").status_code == 403
