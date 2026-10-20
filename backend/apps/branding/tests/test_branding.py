import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import Role
from apps.approvals.models import ApprovalPolicy, ApprovalRequest
from apps.audit.models import AuditEvent
from apps.branding.models import BrandingVersion
from apps.branding.schema import DEFAULT_CONFIG
from conftest import upload

pytestmark = pytest.mark.django_db

BRANDING = "/api/v1/branding/"


def save_draft(client, **changes):
    config = {**client.get(BRANDING).json()["draft"]["config"], **changes}
    return client.put(f"{BRANDING}draft/", {"config": config}, format="json")


def publish(client, label="", reason=""):
    return client.post(f"{BRANDING}publish/", {"label": label, "reason": reason}, format="json")


def test_overview_starts_with_default_draft(admin_client):
    data = admin_client.get(BRANDING).json()
    assert data["current"] is None and data["versions"] == []
    assert data["draft"]["config"]["invoice_template"] == DEFAULT_CONFIG["invoice_template"]
    assert data["has_unpublished_changes"] is True
    assert data["numbering"]["next_invoice"].startswith("INV-")


def test_draft_validation(admin_client):
    assert save_draft(admin_client, brand_color="red").status_code == 400
    assert save_draft(admin_client, invoice_template="fancy").status_code == 400
    assert save_draft(admin_client, logo_size=500).status_code == 400
    assert (
        save_draft(admin_client, custom_fields=[{"label": "BIN", "value": "1"}] * 7).status_code
        == 400
    )


def test_publish_requires_company(admin_client):
    response = publish(admin_client)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "company_required"


def test_publish_creates_immutable_versions_and_preserves_history(admin_client, company):
    admin_client.post("/api/v1/company/logo/", {"file": upload()}, format="multipart")
    save_draft(
        admin_client,
        invoice_template="ledger",
        brand_color="#1f2937",
        payment_instructions="Bank: Example Bank\nAccount: 0001",
    )
    first = publish(admin_client, "Launch identity")
    assert first.status_code == 201
    v1 = first.json()["version"]
    assert v1["number"] == 1 and v1["config"]["brand_color"] == "#1F2937"
    assert v1["company"]["display_name"] == "NetaMate" and v1["logo_url"]

    # Draft edits do not touch the published version.
    save_draft(admin_client, invoice_template="atlas", accent_color="#FF0000")
    assert admin_client.get(BRANDING).json()["has_unpublished_changes"] is True
    assert admin_client.get(f"{BRANDING}versions/1/").json()["config"]["invoice_template"] == (
        "ledger"
    )

    second = publish(admin_client, "Refresh").json()["version"]
    assert second["number"] == 2 and second["config"]["invoice_template"] == "atlas"
    overview = admin_client.get(BRANDING).json()
    assert overview["current"]["number"] == 2
    assert [v["number"] for v in overview["versions"]] == [2, 1]
    assert overview["has_unpublished_changes"] is False
    assert AuditEvent.objects.filter(action="branding.published").count() == 2


def test_database_rejects_rewriting_published_versions(admin_client, company):
    publish(admin_client)
    version = BrandingVersion.objects.get(number=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        BrandingVersion.objects.filter(pk=version.pk).update(label="tampered")
    with pytest.raises(IntegrityError), transaction.atomic():
        BrandingVersion.objects.filter(pk=version.pk).delete()


def test_restore_creates_new_version(admin_client, company):
    save_draft(admin_client, invoice_template="ledger")
    publish(admin_client)
    save_draft(admin_client, invoice_template="atlas")
    publish(admin_client)
    response = admin_client.post(f"{BRANDING}versions/1/restore/")
    assert response.status_code == 201
    restored = response.json()["version"]
    assert restored["number"] == 3 and restored["restored_from"] == 1
    assert restored["config"]["invoice_template"] == "ledger"
    assert BrandingVersion.objects.count() == 3


def test_assets_and_discard(admin_client, company):
    sig = admin_client.post(
        f"{BRANDING}draft/assets/signature/", {"file": upload()}, format="multipart"
    ).json()
    assert sig["draft"]["signature_url"]
    seal = admin_client.post(
        f"{BRANDING}draft/assets/seal/", {"file": upload()}, format="multipart"
    ).json()
    assert seal["draft"]["config"]["seal"]["mode"] == "image"
    publish(admin_client)
    removed = admin_client.delete(f"{BRANDING}draft/assets/seal/").json()
    assert removed["draft"]["seal_image_url"] is None
    assert removed["draft"]["config"]["seal"]["mode"] == "none"
    # The published version still has its seal.
    assert removed["current"]["seal_image_url"]
    discarded = admin_client.post(f"{BRANDING}draft/discard/").json()
    assert discarded["draft"]["seal_image_url"] and not discarded["has_unpublished_changes"]
    assert (
        admin_client.post(
            f"{BRANDING}draft/assets/other/", {"file": upload()}, format="multipart"
        ).status_code
        == 404
    )


def test_branding_permissions(make_user, client_for, company):
    accountant = client_for(make_user("acc", "accountant"))  # company.view only
    assert accountant.get(BRANDING).status_code == 200
    assert save_draft(accountant).status_code == 403
    assert publish(accountant).status_code == 403
    viewer = client_for(make_user("v1", "viewer"))
    assert viewer.get(BRANDING).status_code == 403


# --- Approval enforcement -------------------------------------------------------------


@pytest.fixture
def approval_policy():
    policy = ApprovalPolicy.objects.get(category="admin_changes")
    policy.is_required = True
    policy.approver_role = Role.objects.get(key="finance_manager")
    policy.save()
    return policy


def test_publication_waits_for_approval(
    admin_client, company, approval_policy, make_user, client_for
):
    save_draft(admin_client, invoice_template="ledger")
    response = publish(admin_client, "Needs approval", "New colours")
    assert response.status_code == 202
    request_id = response.json()["request"]["id"]
    assert BrandingVersion.objects.count() == 0
    assert publish(admin_client).status_code == 409  # one pending at a time

    # The draft keeps changing; the approver approves what was requested.
    save_draft(admin_client, invoice_template="atlas")

    # Requester cannot self-approve; a viewer is not an approver.
    denied = admin_client.post(
        f"/api/v1/approvals/requests/{request_id}/approve/", {}, format="json"
    )
    assert denied.status_code == 403
    viewer = client_for(make_user("v1", "viewer"))
    assert (
        viewer.post(
            f"/api/v1/approvals/requests/{request_id}/approve/", {}, format="json"
        ).status_code
        == 403
    )
    assert AuditEvent.objects.filter(action="approval.decision_denied").count() == 2

    approver = client_for(make_user("fm", "finance_manager"))
    inbox = approver.get("/api/v1/approvals/requests/", {"actionable": "true"}).json()
    assert [r["id"] for r in inbox["results"]] == [request_id]
    approved = approver.post(
        f"/api/v1/approvals/requests/{request_id}/approve/",
        {"reason": "Looks right"},
        format="json",
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    version = BrandingVersion.objects.get()
    assert version.config["invoice_template"] == "ledger"
    assert version.published_by.username == "admin"
    assert version.approval_request_id == request_id


def test_rejection_requires_reason_and_publishes_nothing(
    admin_client, company, approval_policy, make_user, client_for
):
    request_id = publish(admin_client).json()["request"]["id"]
    approver = client_for(make_user("fm", "finance_manager"))
    url = f"/api/v1/approvals/requests/{request_id}/reject/"
    assert approver.post(url, {"reason": ""}, format="json").status_code == 400
    assert approver.post(url, {"reason": "Wrong colours"}, format="json").status_code == 200
    assert BrandingVersion.objects.count() == 0
    assert ApprovalRequest.objects.get().status == "rejected"
    assert approver.post(url, {"reason": "again"}, format="json").status_code == 403


def test_self_approval_when_policy_allows(admin_client, company, approval_policy):
    approval_policy.allow_self_approval = True
    approval_policy.save()
    request_id = publish(admin_client).json()["request"]["id"]
    response = admin_client.post(
        f"/api/v1/approvals/requests/{request_id}/approve/", {}, format="json"
    )
    assert response.status_code == 200
    assert BrandingVersion.objects.count() == 1


def test_requester_can_withdraw(admin_client, company, approval_policy):
    request_id = publish(admin_client).json()["request"]["id"]
    assert (
        admin_client.post(f"/api/v1/approvals/requests/{request_id}/cancel/").json()["status"]
        == "cancelled"
    )
    assert publish(admin_client).status_code == 202


def test_overview_reports_document_display_settings(admin_client, company):
    admin_client.patch(
        "/api/v1/settings/business/",
        {"currency_display": "symbol", "number_grouping": "south_asian", "tax_label": "VAT"},
        format="json",
    )
    display = admin_client.get(BRANDING).json()["display"]
    assert display == {
        "currency": "BDT",
        "symbol": "৳",
        "currency_display": "symbol",
        "number_grouping": "south_asian",
        "tax_label": "VAT",
    }
