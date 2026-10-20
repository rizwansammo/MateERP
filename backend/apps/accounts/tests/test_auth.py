import json

import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from conftest import PASSWORD, csrf_client

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
ME = "/api/v1/auth/me/"


def login(client, identifier, password=PASSWORD, remember=False):
    response = client.post(
        LOGIN, {"identifier": identifier, "password": password, "remember": remember}, format="json"
    )
    # Django rotates the CSRF token on sign-in; a browser simply re-reads the
    # cookie, so the test client does the same.
    if response.status_code == 200:
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["mateerp_csrftoken"].value)
    return response


def test_csrf_endpoint_sets_readable_cookie():
    client = APIClient()
    response = client.get("/api/v1/auth/csrf/")
    assert response.status_code == 200
    cookie = client.cookies["mateerp_csrftoken"]
    assert cookie.value and not cookie["httponly"]


def test_login_without_csrf_token_is_rejected(make_user):
    make_user("alice")
    client = APIClient(enforce_csrf_checks=True)
    response = login(client, "alice")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_login_with_csrf_creates_rotated_http_only_session(make_user):
    make_user("alice")
    client = csrf_client()
    client.get("/api/v1/auth/session/")
    response = login(client, "alice")

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert PASSWORD not in json.dumps(body)
    assert not {"password", "password_hash"} & set(body)
    session = client.cookies["mateerp_session"]
    assert session["httponly"]
    assert client.get("/api/v1/auth/session/").json()["authenticated"] is True


def test_login_by_email_is_case_insensitive(make_user):
    make_user("alice", email="Alice@Example.test")
    assert login(csrf_client(), "alice@EXAMPLE.test").status_code == 200


@pytest.mark.parametrize("identifier,password", [("alice", "wrong-password"), ("nobody", PASSWORD)])
def test_failed_login_is_generic(make_user, identifier, password):
    make_user("alice")
    response = login(csrf_client(), identifier, password)
    assert response.status_code == 401
    assert response.json()["error"] == {
        "code": "invalid_credentials",
        "message": "The username or password is incorrect.",
        "details": None,
        "request_id": response["X-Request-ID"],
    }


def test_inactive_user_cannot_sign_in(make_user):
    make_user("alice", active=False)
    assert login(csrf_client(), "alice").status_code == 401


def test_remember_me_extends_session(make_user, settings):
    make_user("alice")
    client = csrf_client()
    login(client, "alice", remember=True)
    assert client.cookies["mateerp_session"]["max-age"] == settings.SESSION_REMEMBER_AGE

    other = csrf_client()
    login(other, "alice", remember=False)
    assert other.cookies["mateerp_session"]["max-age"] == ""  # browser-session cookie


def test_logout_invalidates_server_session(make_user):
    make_user("alice")
    client = csrf_client()
    login(client, "alice")
    stolen_cookie = client.cookies["mateerp_session"].value

    assert client.post("/api/v1/auth/logout/").status_code == 204

    replay = APIClient()
    replay.cookies["mateerp_session"] = stolen_cookie
    response = replay.get(ME)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert response["WWW-Authenticate"]


def test_logout_requires_csrf(make_user):
    make_user("alice")
    client = csrf_client()
    login(client, "alice")
    client.credentials()  # drop the CSRF header
    assert client.post("/api/v1/auth/logout/").json()["error"]["code"] == "csrf_failed"


def test_state_change_without_csrf_is_rejected_for_signed_in_user(make_user):
    make_user("alice")
    client = csrf_client()
    login(client, "alice")
    client.credentials()
    response = client.patch(ME, {"first_name": "Mallory"}, format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_password_change_keeps_current_session_and_ends_others(make_user):
    make_user("alice")
    first, second = csrf_client(), csrf_client()
    login(first, "alice")
    login(second, "alice")

    response = first.post(
        "/api/v1/auth/password/",
        {"current_password": PASSWORD, "new_password": "Brand-New-Ledger-77"},
        format="json",
    )
    assert response.status_code == 200
    assert first.get(ME).status_code == 200
    assert second.get(ME).status_code == 401
    assert login(csrf_client(), "alice", "Brand-New-Ledger-77").status_code == 200


def test_password_change_validates(make_user, client_for):
    client = client_for(make_user("alice"))
    wrong = client.post(
        "/api/v1/auth/password/",
        {"current_password": "nope", "new_password": "Brand-New-Ledger-77"},
        format="json",
    )
    assert "current_password" in wrong.json()["error"]["details"]
    weak = client.post(
        "/api/v1/auth/password/",
        {"current_password": PASSWORD, "new_password": "12345"},
        format="json",
    )
    assert "new_password" in weak.json()["error"]["details"]


def test_forced_password_change_blocks_everything_else(make_user, client_for):
    client = client_for(make_user("alice", "administrator", must_change=True))
    blocked = client.get("/api/v1/users/")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"
    assert client.get(ME).status_code == 200

    client.post(
        "/api/v1/auth/password/",
        {"current_password": PASSWORD, "new_password": "Brand-New-Ledger-77"},
        format="json",
    )
    assert client.get("/api/v1/users/").status_code == 200


def test_profile_update_cannot_change_role(make_user, client_for):
    user = make_user("alice")
    client = client_for(user)
    response = client.patch(
        ME,
        {"first_name": "Alicia", "role": 1, "preferences": {"theme": "dark", "rows_per_page": 50}},
        format="json",
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.first_name == "Alicia"
    assert user.role.key == "viewer"
    assert user.preferences == {"theme": "dark", "rows_per_page": 50}


def test_auth_events_are_audited_without_secrets(make_user):
    make_user("alice")
    login(csrf_client(), "alice", "wrong-password")
    login(csrf_client(), "alice")
    actions = list(AuditEvent.objects.values_list("action", flat=True))
    assert "auth.login.failed" in actions and "auth.login.succeeded" in actions
    dump = json.dumps(list(AuditEvent.objects.values()), default=str)
    assert PASSWORD not in dump and "wrong-password" not in dump


def test_unknown_identifier_is_not_recorded_verbatim(make_user):
    login(csrf_client(), "my-secret-typed-in-username-box")
    event = AuditEvent.objects.get(action="auth.login.failed")
    assert event.target_label == "unknown identifier"
    assert "my-secret" not in json.dumps(list(AuditEvent.objects.values()), default=str)
