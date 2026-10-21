import pytest

from apps.accounting.models import JournalEntry
from apps.company.models import FinancialParty
from apps.founders.models import CorporateTransaction
from conftest import upload

pytestmark = pytest.mark.django_db


def test_party_creation_validation_and_update(admin_client, company):
    response = admin_client.post(
        "/api/v1/founders/parties/",
        {
            "name": "Actual founder",
            "kind": "individual",
            "joined": "2026-01-01",
            "is_founder": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    pk = response.data["id"]
    updated = admin_client.patch(
        f"/api/v1/founders/parties/{pk}/",
        {"display_name": "Founder", "is_active": False},
        format="json",
    )
    assert updated.status_code == 200, updated.data
    assert not FinancialParty.objects.get(pk=pk).is_active
    invalid = admin_client.post(
        "/api/v1/founders/parties/",
        {
            "name": "Invalid dates",
            "kind": "individual",
            "joined": "2026-01-02",
            "left": "2026-01-01",
        },
        format="json",
    )
    assert invalid.status_code == 400


@pytest.mark.parametrize(
    "path",
    [
        "founders/overview/",
        "founders/transactions/",
        "founders/settlements/",
        "founders/plans/",
        "founders/obligations/",
        "ownership/proposals/",
        "ownership/register/",
    ],
)
def test_ordinary_finance_viewer_has_no_founder_access(client_for, make_user, path):
    response = client_for(make_user("ordinary-viewer")).get(f"/api/v1/{path}")
    assert response.status_code == 403


def test_real_api_transaction_workflow_and_private_file_policy(
    founder_books, client_for, make_user
):
    f = founder_books
    client, verifier = client_for(f.request.user), client_for(f.reviewer.user)
    response = client.post(
        "/api/v1/founders/transactions/",
        {
            "client_key": "api-company-receipt",
            "kind": "receipt",
            "classification": "pending",
            "party_id": f.a.pk,
            "date": "2026-02-01",
            "currency": "BDT",
            "amount": "1200",
            "bank_id": f.bank.pk,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    pk = response.data["id"]
    assert (
        client.post(f"/api/v1/founders/transactions/{pk}/verify/", {}, format="json").status_code
        == 403
    )
    quote = verifier.post(f"/api/v1/founders/transactions/{pk}/preview/", {}, format="json")
    assert quote.status_code == 200, quote.data
    result = verifier.post(
        f"/api/v1/founders/transactions/{pk}/verify/",
        {"quote_fingerprint": quote.data["quote_fingerprint"]},
        format="json",
    )
    assert result.status_code == 200, result.data
    assert result.data["status"] == "posted"
    evidence = client.post(
        "/api/v1/founders/evidence/",
        {"title": "Private payment evidence", "transaction_id": pk, "file": upload()},
        format="multipart",
    )
    assert evidence.status_code == 201, evidence.data
    url = evidence.data["file"]["url"]
    assert client.get(url).status_code == 200
    hidden = client_for(make_user("ordinary-accountant", "accountant"))
    assert hidden.get(url).status_code == 404
    assert hidden.get("/api/v1/founders/evidence/").data["count"] == 0
    assert hidden.get(f"/api/v1/founders/transactions/{pk}/").status_code == 403


def test_financial_input_invalid_amount_never_posts(founder_books, client_for):
    f = founder_books
    response = client_for(f.request.user).post(
        "/api/v1/founders/transactions/",
        {
            "client_key": "bad-company-receipt",
            "kind": "receipt",
            "classification": "pending",
            "party_id": f.a.pk,
            "date": "2026-02-01",
            "currency": "BDT",
            "amount": "0.001",
            "bank_id": f.bank.pk,
        },
        format="json",
    )
    assert response.status_code == 400, response.data
    assert not CorporateTransaction.objects.exists()
    assert not JournalEntry.objects.exists()


def test_linking_an_erp_account_requires_identity_administration(
    founder_books, user_with, client_for
):
    f = founder_books
    restricted = user_with("party-editor", "founder.view", "founder.transactions.manage")
    response = client_for(restricted).patch(
        f"/api/v1/founders/parties/{f.a.pk}/", {"user_id": restricted.pk}, format="json"
    )
    assert response.status_code == 403
    f.a.refresh_from_db()
    assert f.a.user_id == f.request.user.pk


def test_statement_pagination_export_and_general_ledger_metadata_scope(
    founder_books, client_for, user_with
):
    from .test_corporate import receipt

    f = founder_books
    posted = receipt(f)
    client = client_for(f.request.user)
    response = client.get("/api/v1/founders/statements/?page_size=1")
    assert response.status_code == 200 and response.data["count"] == 1
    assert response.data["results"][0]["balance"].startswith("20000")
    exported = client.get("/api/v1/founders/statements/?export=csv")
    assert exported.status_code == 200 and "text/csv" in exported["Content-Type"]
    viewer = user_with("statement-reader", "founder.view", "finance.view")
    restricted = client_for(viewer)
    assert restricted.get("/api/v1/founders/statements/?export=csv").status_code == 403
    accountant = client_for(user_with("general-ledger-only", "finance.view"))
    response = accountant.get(f"/api/v1/accounting/journals/{posted.journal_id}/")
    assert response.status_code == 200
    assert all("founder" not in line["dimensions"] for line in response.data["lines"])
    assert {line["base_credit"] for line in response.data["lines"]} == {"20000.000000", "0.000000"}


def test_nonexistent_and_ambiguous_evidence_targets_are_rejected(founder_books, client_for):
    client = client_for(founder_books.request.user)
    response = client.post(
        "/api/v1/founders/evidence/",
        {
            "title": "Missing source",
            "transaction_id": 999999,
            "file": upload(),
        },
        format="multipart",
    )
    assert response.status_code == 404
    response = client.post(
        "/api/v1/founders/evidence/",
        {
            "title": "Ambiguous",
            "transaction_id": 999999,
            "loan_id": 999999,
            "file": upload(),
        },
        format="multipart",
    )
    assert response.status_code == 400


def test_personal_allocation_amounts_remain_exact_strings_in_json(founder_books, client_for):
    from apps.founders.services import sharing

    f = founder_books
    policy = sharing.save_policy(
        f.request,
        {
            "name": "Exact huge personal amounts",
            "basis": "equal",
            "effective_from": "2026-01-01",
            "weights": {str(f.a.pk): "1", str(f.b.pk): "1"},
        },
    )
    sharing.activate(f.request, policy.pk)
    source = sharing.allocate_expense(
        f.request,
        {
            "payer_id": f.a.pk,
            "date": "2026-02-01",
            "currency": "BDT",
            "amount": "999999999999999999.99",
            "description": "Exact amount boundary",
        },
    )
    obligation = source.obligations.get()
    response = client_for(f.request.user).post(
        "/api/v1/founders/settlements/",
        {
            "payer_id": f.b.pk,
            "recipient_id": f.a.pk,
            "date": "2026-02-02",
            "currency": "BDT",
            "amount": str(obligation.amount),
            "allocations": [{"obligation_id": obligation.pk, "amount": str(obligation.amount)}],
            "client_key": "huge-personal-allocation",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.json()["allocations"][0]["amount"] == str(obligation.amount)
    assert not JournalEntry.objects.exists()
