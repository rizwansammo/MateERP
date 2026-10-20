from datetime import date

import pytest

from apps.accounting.services.setup import create_year
from apps.billing.services import payments
from apps.billing.tests.conftest import DAY, as_user, issued
from apps.documents.models import FiledDocument
from apps.documents.services import generate_pdf

pytestmark = pytest.mark.django_db


def test_one_receipt_is_discoverable_in_every_invoice_year_bundle(commerce, client_for):
    create_year(commerce.admin, date(2025, 1, 1))
    lines = [
        {
            "description": "Consulting",
            "unit_price": "10000",
            "revenue_account_id": commerce.books.accounts["4100"].pk,
        }
    ]
    first = issued(commerce, issue_date=date(2025, 12, 15), lines=lines)
    second = issued(commerce, lines=lines)
    third = issued(commerce, lines=lines)
    payment = payments.record_payment(
        as_user(commerce.users.recorder),
        {
            "customer_id": commerce.customer.pk,
            "bank_account_id": commerce.bank.pk,
            "payment_date": DAY,
            "amount": "30000",
            "allocations": [
                {"invoice_id": first.pk, "amount": "10000"},
                {"invoice_id": second.pk, "amount": "10000"},
                {"invoice_id": third.pk, "amount": "10000"},
            ],
        },
        "multiple-invoice-years",
    )
    payment = payments.verify_payment(as_user(commerce.users.verifier), payment.pk)
    generate_pdf("receipt", payment.receipt.pk)
    document = FiledDocument.objects.get(kind="receipt")
    client = client_for(commerce.users.viewer)
    tree = client.get("/api/v1/documents/client-tree/").json()
    assert {y["year"] for y in tree} == {2025, 2026}
    assert all(y["count"] == 1 for y in tree)
    for invoice in (first, second, third):
        response = client.get(
            f"/api/v1/documents/?area=client&year={invoice.issue_date.year}&invoice={invoice.pk}"
        )
        assert [r["id"] for r in response.json()["results"]] == [document.pk]
        node = next(y for y in tree if y["year"] == invoice.issue_date.year)
        assert invoice.pk in {i["id"] for i in node["clients"][0]["invoices"]}
    assert FiledDocument.objects.filter(kind="receipt").count() == 1
    assert client.get("/api/v1/documents/?area=client&unlinked=1").json()["count"] == 0
    original_file = document.file_id
    generate_pdf("receipt", payment.receipt.pk)
    assert FiledDocument.objects.get(pk=document.pk).file_id == original_file


def test_filing_choices_are_identity_only_and_area_authorized(commerce, client_for, user_with):
    invoice = issued(commerce)
    clerk = user_with("filing-only", "documents.client.view", "documents.manage")
    client = client_for(clerk)
    response = client.get(f"/api/v1/documents/references/?area=client&party={commerce.customer.pk}")
    assert response.status_code == 200
    assert response.json()["invoice_id"] == [{"value": str(invoice.pk), "label": invoice.number}]
    assert all(set(row) == {"value", "label"} for row in response.json()["parties"])
    assert client.get("/api/v1/documents/references/?area=vendor").status_code == 403
    reader = client_for(user_with("filing-reader", "documents.client.view"))
    assert reader.get("/api/v1/documents/references/?area=client").status_code == 403


@pytest.mark.parametrize("field", ["year", "month", "invoice", "customer", "vendor_payment"])
def test_invalid_numeric_folder_filters_return_validation_errors(commerce, client_for, field):
    response = client_for(commerce.users.viewer).get(f"/api/v1/documents/?{field}=invalid")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
