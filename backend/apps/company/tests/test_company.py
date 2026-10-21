import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from apps.company.models import CompanyProfile
from apps.company.services import is_module_enabled
from conftest import image_bytes, upload

pytestmark = pytest.mark.django_db

COMPANY = "/api/v1/company/"


def test_missing_company_reports_not_configured(admin_client):
    response = admin_client.get(COMPANY)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "company_not_configured"
    assert admin_client.get(f"{COMPANY}summary/").json()["configured"] is False


def test_create_then_second_company_is_rejected(admin_client, company):
    assert company["display_name"] == "NetaMate"
    assert company["legal_name"] == ""  # unregistered businesses are allowed
    response = admin_client.post(COMPANY, {"display_name": "Another Co"}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "company_exists"
    assert CompanyProfile.objects.count() == 1


def test_database_enforces_single_company(company):
    with pytest.raises(IntegrityError), transaction.atomic():
        CompanyProfile.objects.create(id=2, display_name="Second")


def test_update_persists_and_is_audited(admin_client, company):
    response = admin_client.patch(
        COMPANY,
        {
            "legal_name": "NetaMate Technologies",
            "time_zone": "Asia/Singapore",
            "fiscal_year_start_month": 7,
        },
        format="json",
    )
    assert response.status_code == 200
    fresh = admin_client.get(COMPANY).json()
    assert fresh["time_zone"] == "Asia/Singapore" and fresh["fiscal_year_start_month"] == 7
    event = AuditEvent.objects.get(action="company.updated")
    assert (
        event.before["time_zone"] == "Asia/Dhaka" and event.after["time_zone"] == "Asia/Singapore"
    )


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"base_currency": "XYZ"}, "base_currency"),
        ({"time_zone": "Mars/Base"}, "time_zone"),
        ({"display_name": " "}, "display_name"),
        ({"fiscal_year_start_month": 13}, "fiscal_year_start_month"),
        ({"phone": "call me <script>"}, "phone"),
        ({"website": "not a url"}, "website"),
    ],
)
def test_validation(admin_client, company, payload, field):
    response = admin_client.patch(COMPANY, payload, format="json")
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


def test_permissions(make_user, client_for, company):
    viewer = client_for(make_user("v1", "viewer"))
    assert viewer.get(COMPANY).status_code == 403
    assert viewer.patch(COMPANY, {"display_name": "Hacked"}, format="json").status_code == 403
    accountant = client_for(make_user("acc", "accountant"))
    assert accountant.get(COMPANY).status_code == 200  # company.view
    assert accountant.patch(COMPANY, {"display_name": "X"}, format="json").status_code == 403
    # Every signed-in user sees the identity in the app chrome.
    assert viewer.get(f"{COMPANY}summary/").json()["display_name"] == "NetaMate"


def test_logo_upload_replace_and_visibility(admin_client, company, make_user, client_for):
    response = admin_client.post(f"{COMPANY}logo/", {"file": upload()}, format="multipart")
    assert response.status_code == 200
    first_url = response.json()["logo"]["url"]

    viewer = client_for(make_user("v1", "viewer"))
    summary = viewer.get(f"{COMPANY}summary/").json()
    assert summary["logo_url"] == first_url
    assert viewer.get(first_url).status_code == 200

    second = admin_client.post(
        f"{COMPANY}logo/",
        {"file": upload("new.webp", image_bytes("WEBP"), "image/webp")},
        format="multipart",
    )
    assert second.json()["logo"]["url"] != first_url
    assert AuditEvent.objects.filter(action="company.logo_replaced").exists()


@pytest.mark.parametrize(
    "name,data,ctype",
    [
        ("logo.png", b"not really an image", "image/png"),
        (
            "logo.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
            "image/svg+xml",
        ),
        ("logo.gif", image_bytes("GIF"), "image/gif"),
        ("big.png", b"\x89PNG" + b"0" * (2 * 1024 * 1024 + 10), "image/png"),
    ],
)
def test_unsafe_logo_uploads_rejected(admin_client, company, name, data, ctype):
    response = admin_client.post(
        f"{COMPANY}logo/", {"file": upload(name, data, ctype)}, format="multipart"
    )
    assert response.status_code == 400
    assert "file" in response.json()["error"]["details"]


def test_business_settings_and_numbering_validation(admin_client, company):
    url = "/api/v1/settings/business/"
    settings = admin_client.get(url).json()
    assert settings["enabled_currencies"][0] == "BDT"
    assert settings["numbering"]["invoice"] == "INV-{YYYY}-{####}"

    ok = admin_client.patch(
        url,
        {
            "enabled_currencies": ["USD"],
            "default_tax_rate": "15.00",
            "numbering": {"invoice": "NM-INV-{YY}{MM}-{#####}"},
        },
        format="json",
    )
    assert ok.status_code == 200
    assert ok.json()["enabled_currencies"] == ["BDT", "USD"]  # base always enabled

    for bad in (
        {"invoice": "INV-{YYYY}"},
        {"receipt": "NM-INV-{YYYY}-{####}"},
        {"invoice": "{####}"},
        {"invoice": "INV-<script>-{###}"},
    ):
        response = admin_client.patch(url, {"numbering": bad}, format="json")
        assert response.status_code == 400, bad

    preview = admin_client.get("/api/v1/settings/numbering/preview/").json()["examples"]
    assert preview["invoice"].startswith("NM-INV-") and preview["invoice"].endswith("-00001")


def test_modules_toggle_persist_and_are_server_side(admin_client, make_user, client_for):
    modules = {m["key"]: m for m in admin_client.get("/api/v1/modules/").json()["optional"]}
    assert modules["inventory"]["enabled"] and modules["inventory"]["implemented"]
    assert all(m["implemented"] for m in modules.values())

    response = admin_client.put("/api/v1/modules/inventory/", {"enabled": False}, format="json")
    assert response.status_code == 200 and response.json()["enabled"] is False
    assert is_module_enabled("inventory") is False
    assert AuditEvent.objects.filter(action="settings.module_disabled").exists()

    # Core modules cannot be toggled; viewers cannot toggle anything.
    assert (
        admin_client.put(
            "/api/v1/modules/accounting/", {"enabled": False}, format="json"
        ).status_code
        == 404
    )
    viewer = client_for(make_user("v1", "viewer"))
    assert (
        viewer.put("/api/v1/modules/inventory/", {"enabled": True}, format="json").status_code
        == 403
    )
    assert viewer.get("/api/v1/modules/").status_code == 200
