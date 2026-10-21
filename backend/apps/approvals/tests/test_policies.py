import pytest

from apps.accounts.models import Role
from apps.approvals.catalog import CATEGORIES
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

URL = "/api/v1/approvals/policies/"


def test_all_categories_listed_with_honest_enforcement(admin_client):
    policies = admin_client.get(URL).json()
    assert [p["category"] for p in policies] == [c.key for c in CATEGORIES]
    enforced = {p["category"]: p["enforced"] for p in policies}
    assert enforced["admin_changes"] is True
    for phase4 in ("expenses", "invoices", "client_payments", "credits_refunds", "vendor_payments"):
        assert enforced[phase4] is True
    assert enforced["purchase_orders"] is True  # Phase 6 now executes frozen order approval.


def test_update_policy_is_audited(admin_client):
    role = Role.objects.get(key="finance_manager")
    response = admin_client.patch(
        f"{URL}expenses/",
        {"is_required": True, "approver_role": role.pk, "amount_threshold": "50000.00"},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approver_role"]["name"] == "Finance Manager"
    assert body["amount_threshold"] == "50000.00"
    assert AuditEvent.objects.filter(action="approval.policy_updated").exists()


def test_validation(admin_client):
    assert (
        admin_client.patch(
            f"{URL}admin_changes/", {"amount_threshold": "10.00"}, format="json"
        ).status_code
        == 400
    )
    assert (
        admin_client.patch(f"{URL}expenses/", {"amount_threshold": "-1"}, format="json").status_code
        == 400
    )
    custom = Role.objects.create(key="old", name="Old", is_active=False)
    assert (
        admin_client.patch(
            f"{URL}expenses/", {"approver_role": custom.pk}, format="json"
        ).status_code
        == 400
    )
    assert admin_client.patch(f"{URL}nonexistent/", {}, format="json").status_code == 404


def test_requires_approvals_manage(make_user, client_for):
    client = client_for(make_user("acc", "accountant"))
    assert client.get(URL).status_code == 403
    assert client.patch(f"{URL}expenses/", {"is_required": True}, format="json").status_code == 403
