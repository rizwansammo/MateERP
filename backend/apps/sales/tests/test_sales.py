"""Scenario A: customers, contacts, projects and sales orders (no ledger effect)."""

import pytest

from apps.accounting.models import JournalEntry
from apps.audit.models import AuditEvent
from apps.sales.models import Customer, SalesOrder

pytestmark = pytest.mark.django_db
BASE = "/api/v1/sales/"


@pytest.fixture
def seller(user_with):
    return user_with("seller", "finance.view", "sales.manage")


def create_customer(client, **extra):
    response = client.post(
        f"{BASE}customers/",
        {"name": "Acme Trading Ltd", "currency": "BDT", "payment_terms_days": 30, **extra},
        format="json",
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_customer_lifecycle_and_permissions(books, client_for, seller, user_with):
    client = client_for(seller)
    first = create_customer(client, email="ap@acme.test")
    second = create_customer(client, name="Beta Labs")
    assert (first["code"], second["code"]) == ("CUS-00001", "CUS-00002")
    viewer = client_for(user_with("viewer", "finance.view"))
    assert viewer.get(f"{BASE}customers/?search=acme").json()["count"] == 1
    assert viewer.post(f"{BASE}customers/", {"name": "X"}, format="json").status_code == 403
    outsider = client_for(user_with("outsider", "sales.manage"))
    assert outsider.get(f"{BASE}customers/").status_code == 403
    bad = client.post(f"{BASE}customers/", {"name": "Y", "currency": "XYZ"}, format="json")
    assert bad.status_code == 400
    patched = client.patch(
        f"{BASE}customers/{first['id']}/", {"code": "HACK", "city": "Dhaka"}, format="json"
    )
    assert patched.json()["code"] == "CUS-00001" and patched.json()["city"] == "Dhaka"
    assert AuditEvent.objects.filter(action="sales.customer_updated").exists()


def test_single_primary_contact(books, client_for, seller):
    client = client_for(seller)
    customer = create_customer(client)
    url = f"{BASE}customers/{customer['id']}/contacts/"
    a = client.post(url, {"name": "Rina", "is_primary": True}, format="json").json()
    client.post(url, {"name": "Tanvir", "is_primary": True}, format="json")
    contacts = client.get(f"{BASE}customers/{customer['id']}/").json()["contacts"]
    assert [c["name"] for c in contacts if c["is_primary"]] == ["Tanvir"]
    assert any(c["id"] == a["id"] and not c["is_primary"] for c in contacts)


def test_project_milestones_allocate_contract_exactly(books, client_for, seller):
    client = client_for(seller)
    customer = create_customer(client)
    body = {
        "reference": "prj-acme-01",
        "name": "ERP rollout",
        "customer_id": customer["id"],
        "currency": "BDT",
        "contract_value": "100000.01",
        "milestones": [
            {"name": "Kick-off", "percent": "30"},
            {"name": "Build", "percent": "40"},
            {"name": "Handover", "percent": "30"},
        ],
    }
    project = client.post(f"{BASE}projects/", body, format="json").json()
    assert project["reference"] == "PRJ-ACME-01"
    amounts = [m["amount"] for m in project["milestones"]]
    assert sum(float(a) for a in amounts) == pytest.approx(100000.01)
    bad = {**body, "reference": "PRJ-2", "milestones": [{"name": "Only", "percent": "90"}]}
    assert client.post(f"{BASE}projects/", bad, format="json").status_code == 400


def test_sales_order_flow_has_no_receivable(books, client_for, seller):
    client = client_for(seller)
    customer = create_customer(client)
    order = client.post(
        f"{BASE}orders/",
        {
            "customer_id": customer["id"],
            "order_date": "2026-10-05",
            "title": "Annual support",
            "lines": [
                {
                    "description": "Support hours",
                    "quantity": "10",
                    "unit_price": "1500",
                    "tax_code_id": books.vat.pk,
                },
            ],
        },
        format="json",
    )
    assert order.status_code == 201, order.json()
    order = order.json()
    assert order["number"] == "SO-2026-001" and order["currency"] == "BDT"
    url = f"{BASE}orders/{order['id']}/"
    stale = client.patch(url, {"revision": 99, "title": "x"}, format="json")
    assert stale.json()["error"]["code"] == "stale_revision"
    edited = client.patch(url, {"revision": 1, "title": "Support 2026"}, format="json").json()
    assert edited["revision"] == 2
    assert client.post(f"{url}confirm/").json()["status"] == "confirmed"
    assert client.patch(url, {"revision": 2, "title": "late"}, format="json").status_code == 409
    assert client.post(f"{url}cancel/", {"reason": ""}, format="json").status_code == 400
    cancelled = client.post(f"{url}cancel/", {"reason": "Client withdrew"}, format="json")
    assert cancelled.json()["status"] == "cancelled"
    assert JournalEntry.objects.count() == 0
    assert SalesOrder.objects.get().status == "cancelled"


def test_calculate_endpoint_returns_decimal_strings(books, client_for, seller):
    response = client_for(seller).post(
        f"{BASE}calculate/",
        {
            "currency": "BDT",
            "date": "2026-10-10",
            "lines": [{"quantity": "1", "unit_price": "10000", "tax_code_id": books.vat.pk}],
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["total"] == "11000.00"
    assert Customer.objects.count() == 0
