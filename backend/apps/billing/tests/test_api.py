"""HTTP contract: CSRF, envelopes, permission gates and the issue → pay → receipt flow."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.billing.models import Invoice
from conftest import PASSWORD

pytestmark = pytest.mark.django_db
BASE = "/api/v1/billing/"


def browser(user: User) -> APIClient:
    """A CSRF-enforcing session client, as the Next proxy forwards a browser."""
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/v1/auth/csrf/")
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["mateerp_csrftoken"].value)
    login = client.post(
        "/api/v1/auth/login/", {"identifier": user.username, "password": PASSWORD}, format="json"
    )
    assert login.status_code == 200, login.json()
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["mateerp_csrftoken"].value)
    return client


def invoice_body(commerce):
    return {
        "customer_id": commerce.customer.pk,
        "issue_date": "2026-10-10",
        "lines": [
            {
                "description": "Consulting",
                "quantity": "1",
                "unit_price": "10000",
                "tax_code_id": commerce.books.vat.pk,
                "revenue_account_id": commerce.books.accounts["4100"].pk,
            }
        ],
    }


def test_full_flow_through_http(commerce):
    issuer = browser(commerce.users.issuer)
    created = issuer.post(f"{BASE}invoices/", invoice_body(commerce), format="json")
    assert created.status_code == 201, created.json()
    invoice = created.json()
    assert (
        invoice["status"] == "draft"
        and invoice["total"] == "11000.000000"
        and invoice["number"] is None
    )
    issued = issuer.post(f"{BASE}invoices/{invoice['id']}/issue/").json()
    assert issued["number"] == "INV-2026-0001" and issued["pdf_status"] == "ready"
    assert issuer.get(issued["pdf_url"]).status_code == 200
    recorder = browser(commerce.users.recorder)
    payment = recorder.post(
        f"{BASE}payments/",
        {
            "customer_id": commerce.customer.pk,
            "bank_account_id": commerce.bank.pk,
            "payment_date": "2026-10-10",
            "amount": "11000",
            "allocations": [{"invoice_id": invoice["id"], "amount": "11000"}],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="http-payment-0001",
    )
    assert payment.status_code == 201, payment.json()
    pid = payment.json()["id"]
    assert recorder.post(f"{BASE}payments/{pid}/verify/").status_code == 403
    verified = browser(commerce.users.verifier).post(f"{BASE}payments/{pid}/verify/").json()
    assert verified["status"] == "verified" and verified["receipt"]["number"] == "MR-2026-0001"
    receipt = issuer.get(f"{BASE}receipts/{verified['receipt']['id']}/").json()
    assert receipt["pdf_status"] == "ready" and receipt["pdf_url"]
    detail = issuer.get(f"{BASE}invoices/{invoice['id']}/").json()
    assert detail["status"] == "paid" and detail["outstanding"] == "0.000000"
    recon = issuer.get(f"{BASE}reconciliation/").json()
    assert recon["receivable"]["difference"] == "0.000000"
    account = issuer.get(f"{BASE}customers/{commerce.customer.pk}/account/").json()
    assert [row["kind"] for row in account["statement"]] == ["Invoice", "Payment"]
    assert account["statement"][-1]["balance"] == "0.000000"


def test_csrf_and_envelope_on_billing_writes(commerce):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(commerce.users.issuer)
    response = client.post(f"{BASE}invoices/", invoice_body(commerce), format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
    issuer = browser(commerce.users.issuer)
    bad = issuer.post(
        f"{BASE}invoices/", {**invoice_body(commerce), "customer_id": 999999}, format="json"
    )
    assert bad.status_code == 400 and set(bad.json()["error"]) == {
        "code",
        "message",
        "details",
        "request_id",
    }


def test_permission_gates(commerce, client_for):
    viewer = client_for(commerce.users.viewer)
    assert viewer.get(f"{BASE}invoices/").status_code == 200
    assert viewer.post(f"{BASE}invoices/", invoice_body(commerce), format="json").status_code == 403
    assert viewer.get(f"{BASE}overview/").status_code == 200
    assert viewer.put(f"{BASE}settings/", {}, format="json").status_code == 403
    clerk = client_for(commerce.users.clerk)
    draft = clerk.post(f"{BASE}invoices/", invoice_body(commerce), format="json").json()
    assert clerk.post(f"{BASE}invoices/{draft['id']}/issue/").status_code == 403
    assert Invoice.objects.get(pk=draft["id"]).number is None
    # Billing staff hold no accounting.manage: the public journal API stays closed.
    assert clerk.post("/api/v1/accounting/journals/", {}, format="json").status_code == 403


def test_overview_and_settings(commerce, admin_client):
    data = admin_client.get(f"{BASE}settings/").json()
    assert data["controls"]["receivable"]["code"] == "1100"
    updated = admin_client.put(
        f"{BASE}settings/",
        {"default_revenue_account_id": commerce.books.accounts["4100"].pk},
        format="json",
    )
    assert updated.json()["default_revenue_account_id"] == commerce.books.accounts["4100"].pk
    bad = admin_client.put(
        f"{BASE}settings/",
        {"default_revenue_account_id": commerce.books.accounts["6100"].pk},
        format="json",
    )
    assert bad.status_code == 400
    overview = admin_client.get(f"{BASE}overview/").json()
    assert overview["base_currency"] == "BDT" and overview["outstanding"] == "0"


def test_project_financials_endpoint(commerce, admin_client):
    project = admin_client.post(
        "/api/v1/sales/projects/",
        {
            "reference": "PRJ-9",
            "name": "Build",
            "customer_id": commerce.customer.pk,
            "currency": "BDT",
            "contract_value": "50000",
            "milestones": [{"name": "All", "percent": "100"}],
        },
        format="json",
    ).json()
    created = admin_client.post(
        f"{BASE}invoices/from-source/",
        {
            "milestone_id": project["milestones"][0]["id"],
            "issue_date": "2026-10-10",
            "revenue_account_id": commerce.books.accounts["4100"].pk,
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    admin_client.post(f"{BASE}invoices/{created.json()['id']}/issue/")
    data = admin_client.get(f"{BASE}projects/{project['id']}/financials/").json()
    assert data["invoiced"] == "50000.000000" and data["uninvoiced"] == "0.000000"
    assert data["milestones"][0]["invoice"]["number"] == "INV-2026-0001"


def test_document_branding_hides_signature_assets_from_finance_users(commerce, client_for):
    viewer = client_for(commerce.users.viewer).get(f"{BASE}document-branding/").json()
    assert viewer["version"] == 1 and viewer["config"]["invoice_template"] == "meridian"
    assert viewer["signature_url"] is None and viewer["seal_image_url"] is None
    assert client_for(commerce.users.viewer).get(f"{BASE}document-branding/?version=99").json() == {
        "version": None
    }
