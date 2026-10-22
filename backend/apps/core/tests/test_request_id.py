from apps.core.services import health


def _ok(monkeypatch):
    monkeypatch.setattr(health, "check_database", lambda: health.CheckResult(health.STATUS_OK, 1.0))


def test_valid_incoming_request_id_is_echoed(api_client, monkeypatch):
    _ok(monkeypatch)
    response = api_client.get("/api/v1/health/", HTTP_X_REQUEST_ID="trace-abc-12345")

    assert response["X-Request-ID"] == "trace-abc-12345"


def test_malformed_request_id_is_replaced(api_client, monkeypatch):
    _ok(monkeypatch)
    response = api_client.get("/api/v1/health/", HTTP_X_REQUEST_ID="bad id\nwith newline")

    assert response["X-Request-ID"] != "bad id\nwith newline"
    assert len(response["X-Request-ID"]) == 32


def test_error_envelope_carries_the_response_request_id(api_client):
    response = api_client.get("/api/v1/nope/")

    assert response.json()["error"]["request_id"] == response["X-Request-ID"]


def test_private_api_errors_disallow_caching(api_client):
    response = api_client.get("/api/v1/nope/")
    assert response["Cache-Control"] == "private, no-store"


def test_explicit_cache_control_is_preserved(api_client, monkeypatch):
    _ok(monkeypatch)
    response = api_client.get("/api/v1/health/")
    assert response["Cache-Control"] == "no-store"
