import pytest


def _assert_envelope(body, code):
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["error"]["request_id"]


def test_unknown_api_route_returns_json_404(api_client):
    response = api_client.get("/api/v1/does-not-exist/")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    _assert_envelope(response.json(), "not_found")


def test_unknown_api_version_returns_json_404(api_client):
    response = api_client.get("/api/v2/health/")

    assert response.status_code == 404
    _assert_envelope(response.json(), "not_found")


@pytest.mark.urls("apps.core.tests.urls")
def test_endpoints_require_authentication_by_default(api_client):
    response = api_client.get("/api/v1/protected/")

    assert response.status_code in (401, 403)
    _assert_envelope(response.json(), "not_authenticated")


@pytest.mark.urls("apps.core.tests.urls")
def test_validation_errors_include_field_details(api_client):
    response = api_client.post("/api/v1/validate/", {"amount": "12.345"}, format="json")

    assert response.status_code == 400
    body = response.json()
    _assert_envelope(body, "validation_error")
    assert "amount" in body["error"]["details"]


@pytest.mark.urls("apps.core.tests.urls")
def test_decimals_are_serialised_as_exact_strings(api_client):
    response = api_client.post("/api/v1/validate/", {"amount": "1000.10"}, format="json")

    assert response.status_code == 200
    assert response.json() == {"amount": "1000.10"}


@pytest.mark.urls("apps.core.tests.urls")
def test_unhandled_errors_return_generic_500(api_client):
    response = api_client.get("/api/v1/boom/")

    assert response.status_code == 500
    body = response.json()
    _assert_envelope(body, "server_error")
    assert "internal detail" not in response.content.decode()
