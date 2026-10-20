import json

import pytest

from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent
from conftest import PASSWORD, csrf_client

pytestmark = pytest.mark.django_db

USERS = "/api/v1/users/"


def role_id(key: str) -> int:
    return Role.objects.get(key=key).pk


def create(client, username="bob", role="viewer", **extra):
    return client.post(
        USERS,
        {
            "username": username,
            "email": f"{username}@example.test",
            "first_name": username.title(),
            "role": role_id(role),
            **extra,
        },
        format="json",
    )


def test_admin_creates_user_with_one_time_temporary_password(admin_client):
    response = create(admin_client)
    assert response.status_code == 201
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    temporary = body["temporary_password"]
    assert len(temporary) >= 16

    user = User.objects.get(username="bob")
    assert user.must_change_password
    assert user.password != temporary and user.check_password(temporary)
    detail = admin_client.get(f"{USERS}{user.pk}/").json()
    assert "temporary_password" not in detail
    assert temporary not in json.dumps(list(AuditEvent.objects.values()), default=str)


def test_new_user_must_change_password_on_first_sign_in(admin_client):
    temporary = create(admin_client).json()["temporary_password"]
    client = csrf_client()
    response = client.post(
        "/api/v1/auth/login/", {"identifier": "bob", "password": temporary}, format="json"
    )
    assert response.json()["must_change_password"] is True
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["mateerp_csrftoken"].value)
    assert client.get("/api/v1/auth/session/").status_code == 200
    assert client.get("/api/v1/company/summary/").json()["error"]["code"] == (
        "password_change_required"
    )


def test_duplicates_are_rejected_case_insensitively(admin_client, make_user):
    make_user("bob")
    response = create(admin_client, "BOB")
    assert response.status_code == 400
    assert "username" in response.json()["error"]["details"]


def test_invalid_username_rejected(admin_client):
    assert create(admin_client, "bad name!").status_code == 400


def test_non_admin_cannot_grant_administrator_or_unheld_permissions(make_user, client_for):
    custom = Role.objects.create(key="user-admin", name="User admin")
    custom.permissions.set(Role.objects.get(key="viewer").permissions.all())
    from apps.accounts.models import Permission

    custom.permissions.add(Permission.objects.get(code="users.manage"))
    client = client_for(make_user("ua", None))
    User.objects.filter(username="ua").update(role=custom)

    assert create(client, "new1", "administrator").status_code == 403
    assert create(client, "new2", "finance_manager").status_code == 403
    assert create(client, "new3", "viewer").status_code == 201


def test_non_admin_cannot_manage_more_privileged_user(make_user, client_for, admin_user):
    from apps.accounts.models import Permission

    custom = Role.objects.create(key="ua", name="UA")
    custom.permissions.set(Permission.objects.filter(code__in=["users.manage", "finance.view"]))
    actor = make_user("ua", None)
    actor.role = custom
    actor.save()
    client = client_for(actor)
    assert client.post(f"{USERS}{admin_user.pk}/deactivate/").status_code == 403
    assert client.post(f"{USERS}{admin_user.pk}/reset-password/").status_code == 403


def test_list_search_filter_sort_and_paginate(admin_client, make_user):
    for name in ("carol", "dave", "erin"):
        make_user(name, "accountant" if name != "erin" else "viewer", active=name != "dave")
    data = admin_client.get(USERS, {"q": "car"}).json()
    assert [u["username"] for u in data["results"]] == ["carol"]
    data = admin_client.get(USERS, {"status": "inactive"}).json()
    assert [u["username"] for u in data["results"]] == ["dave"]
    data = admin_client.get(USERS, {"role": role_id("viewer")}).json()
    assert [u["username"] for u in data["results"]] == ["erin"]
    data = admin_client.get(USERS, {"ordering": "-username", "page_size": 2}).json()
    assert data["count"] == 4 and data["total_pages"] == 2
    assert [u["username"] for u in data["results"]] == ["erin", "dave"]


def test_users_api_requires_permission(make_user, client_for):
    client = client_for(make_user("viewer1"))
    assert client.get(USERS).status_code == 403
    assert create(client).status_code == 403


def test_update_user_and_role_change_audited(admin_client, make_user):
    user = make_user("bob")
    response = admin_client.patch(
        f"{USERS}{user.pk}/", {"first_name": "Robert", "role": role_id("accountant")}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["role"]["name"] == "Accountant"
    assert AuditEvent.objects.filter(action="user.role_changed", target_id=str(user.pk)).exists()


def test_cannot_change_own_role(admin_client, admin_user, make_user):
    make_user("admin2", "administrator")
    response = admin_client.patch(
        f"{USERS}{admin_user.pk}/", {"role": role_id("viewer")}, format="json"
    )
    assert response.status_code == 403


def test_deactivation_ends_existing_session_and_blocks_sign_in(admin_client, make_user):
    user = make_user("bob")
    session = csrf_client()
    session.post("/api/v1/auth/login/", {"identifier": "bob", "password": PASSWORD}, format="json")
    assert session.get("/api/v1/auth/me/").status_code == 200

    assert admin_client.post(f"{USERS}{user.pk}/deactivate/").status_code == 200
    assert session.get("/api/v1/auth/me/").status_code == 401
    relogin = csrf_client().post(
        "/api/v1/auth/login/", {"identifier": "bob", "password": PASSWORD}, format="json"
    )
    assert relogin.status_code == 401
    assert AuditEvent.objects.filter(action="user.deactivated").exists()

    assert admin_client.post(f"{USERS}{user.pk}/activate/").status_code == 200
    assert AuditEvent.objects.filter(action="user.reactivated").exists()


def test_last_administrator_is_protected(admin_client, admin_user, make_user):
    other = make_user("admin2", "administrator")
    # Demote the second admin: allowed, one admin remains.
    assert (
        admin_client.patch(
            f"{USERS}{other.pk}/", {"role": role_id("viewer")}, format="json"
        ).status_code
        == 200
    )
    # Self-deactivation is never allowed.
    response = admin_client.post(f"{USERS}{admin_user.pk}/deactivate/")
    assert response.status_code == 409


def test_last_administrator_cannot_be_deactivated_by_another_admin(make_user, client_for):
    first = make_user("admin1", "administrator")
    second = make_user("admin2", "administrator")
    client = client_for(second)
    assert client.post(f"{USERS}{first.pk}/deactivate/").status_code == 200
    # Now `second` is the only admin; a fresh admin client cannot remove them either.
    first.is_active = True
    first.save()
    client_first = client_for(first)
    second_deactivated = client_first.post(f"{USERS}{second.pk}/deactivate/")
    assert second_deactivated.status_code == 200
    third = client_for(second)
    assert third.get("/api/v1/auth/me/").status_code == 401
    response = client_first.patch(f"{USERS}{first.pk}/", {"role": role_id("viewer")}, format="json")
    assert response.status_code == 403  # cannot change own role


def test_last_admin_demotion_blocked(make_user, client_for):
    only_admin = make_user("solo", "administrator")
    helper = make_user("helper", None)
    from apps.accounts.models import Permission

    role = Role.objects.create(key="mgr", name="Manager")
    role.permissions.set(Permission.objects.all())
    helper.role = role
    helper.save()
    # Even holding every permission, demoting the last administrator is refused.
    response = client_for(helper).patch(
        f"{USERS}{only_admin.pk}/", {"role": role_id("viewer")}, format="json"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_administrator"


def test_reset_password_issues_new_temporary_and_ends_sessions(admin_client, make_user):
    user = make_user("bob")
    session = csrf_client()
    session.post("/api/v1/auth/login/", {"identifier": "bob", "password": PASSWORD}, format="json")
    response = admin_client.post(f"{USERS}{user.pk}/reset-password/")
    assert response.status_code == 200
    assert session.get("/api/v1/auth/me/").status_code == 401
    user.refresh_from_db()
    assert user.must_change_password
    assert user.check_password(response.json()["temporary_password"])
