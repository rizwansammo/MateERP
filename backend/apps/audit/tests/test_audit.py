import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from apps.audit.services import record, redact

pytestmark = pytest.mark.django_db

URL = "/api/v1/audit/events/"


def test_redact_removes_secret_fields_recursively():
    data = {
        "name": "x",
        "password": "p",
        "nested": {"api_key": "k", "csrf_token": "t", "list": [{"session_id": "s", "ok": 1}]},
    }
    assert redact(data) == {
        "name": "x",
        "password": "[redacted]",
        "nested": {
            "api_key": "[redacted]",
            "csrf_token": "[redacted]",
            "list": [{"session_id": "[redacted]", "ok": 1}],
        },
    }


def test_events_are_append_only_in_the_database():
    event = record("test.event", target_label="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).update(action="tampered")
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).delete()


def test_secrets_never_stored_even_if_passed():
    event = record("test.event", after={"password": "hunter2", "label": "ok"})
    assert event.after == {"password": "[redacted]", "label": "ok"}


def test_api_filters_and_pagination(admin_client, admin_user):
    for i in range(30):
        record("user.updated", actor=admin_user, target_label=f"User {i}")
    record("auth.login.failed", target_label="unknown identifier", outcome="failure")

    page = admin_client.get(URL, {"page_size": 10}).json()
    assert page["count"] == 31 and len(page["results"]) == 10 and page["total_pages"] == 4
    assert admin_client.get(URL, {"category": "auth"}).json()["count"] == 1
    assert admin_client.get(URL, {"outcome": "failure"}).json()["count"] == 1
    assert admin_client.get(URL, {"actor": admin_user.pk}).json()["count"] == 30
    assert admin_client.get(URL, {"q": "User 7"}).json()["count"] == 1
    assert (
        admin_client.get(URL, {"date_from": "2000-01-01", "date_to": "2000-12-31"}).json()["count"]
        == 0
    )
    assert admin_client.get(URL, {"date_from": "yesterday"}).status_code == 400
    assert admin_client.get(URL, {"page_size": 1000}).json()["page_size"] == 100
    facets = admin_client.get("/api/v1/audit/facets/").json()
    assert "auth" in facets["categories"]


def test_audit_requires_permission_and_has_no_write_api(make_user, client_for, admin_client):
    viewer = client_for(make_user("v1", "viewer"))
    assert viewer.get(URL).status_code == 403
    assert admin_client.post(URL, {"action": "fake"}, format="json").status_code == 405


def test_events_filter_by_target(admin_client, admin_user):
    from apps.audit.services import record

    record("test.one", target_type="billing.invoice", target_id="7", target_label="Invoice 7")
    record("test.two", target_type="billing.invoice", target_id="8", target_label="Invoice 8")
    rows = admin_client.get("/api/v1/audit/events/?target_type=billing.invoice&target_id=7").json()[
        "results"
    ]
    assert [r["action"] for r in rows] == ["test.one"]
