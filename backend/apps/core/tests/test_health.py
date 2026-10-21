import json

import pytest
from django.db import OperationalError

from apps.core.services import health

URL = "/api/v1/health/"


@pytest.mark.django_db
def test_health_reports_ok_with_live_database(api_client):
    response = api_client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "mateerp-backend"
    assert body["version"] == "0.6.0"
    assert body["environment"] == "test"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["database"]["latency_ms"] >= 0
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_health_does_not_expose_configuration(api_client, settings):
    body = api_client.get(URL).json()
    raw = json.dumps(body)

    assert set(body) == {"status", "service", "version", "environment", "time", "checks"}
    assert set(body["checks"]["database"]) == {"status", "latency_ms"}
    for secret in (settings.DATABASES["default"]["PASSWORD"], settings.SECRET_KEY):
        if secret:
            assert secret not in raw


@pytest.mark.django_db
def test_health_returns_503_when_database_is_unavailable(api_client, monkeypatch):
    def broken_cursor(*args, **kwargs):
        raise OperationalError("connection refused to db-host:5432")

    monkeypatch.setattr(health.connection, "cursor", broken_cursor)

    response = api_client.get(URL)

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == {"status": "unavailable", "latency_ms": None}
    assert "db-host" not in json.dumps(body)


def test_health_needs_no_authentication(api_client, monkeypatch):
    monkeypatch.setattr(health, "check_database", lambda: health.CheckResult(health.STATUS_OK, 1.0))
    assert api_client.get(URL).status_code == 200
