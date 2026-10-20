"""Scenarios N, O, P: client/vendor document trees, upload validation and authorization."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from pypdf import PdfWriter
from pypdf.actions import JavaScript

from apps.audit.models import AuditEvent
from apps.billing.services import payments
from apps.billing.tests.conftest import DAY, as_user, issued
from apps.documents.models import FiledDocument
from apps.documents.services import generate_pdf
from apps.purchasing.services.payables import save_vendor
from conftest import image_bytes

pytestmark = pytest.mark.django_db
URL = "/api/v1/documents/"


def pdf_bytes(*, js=False, password=None):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    if js:
        writer.add_open_action(JavaScript("app.alert(1);"))
    if password:
        writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def upload(client, kind, data, name="proof.pdf", content=None, content_type="application/pdf"):
    payload = SimpleUploadedFile(
        name, content if content is not None else pdf_bytes(), content_type=content_type
    )
    return client.post(URL, {"kind": kind, "file": payload, **data}, format="multipart")


@pytest.fixture
def filed(commerce, client_for, user_with):
    invoice = issued(commerce)
    generate_pdf("invoice", invoice.pk)
    payment = payments.record_payment(
        as_user(commerce.users.recorder),
        {
            "customer_id": commerce.customer.pk,
            "bank_account_id": commerce.bank.pk,
            "payment_date": DAY,
            "amount": "11000",
            "allocations": [{"invoice_id": invoice.pk, "amount": "11000"}],
        },
        "documents-payment-1",
    )
    payment = payments.verify_payment(as_user(commerce.users.verifier), payment.pk)
    generate_pdf("receipt", payment.receipt.pk)
    clerk = user_with("filer", "finance.view", "documents.manage", "banking.evidence.view")
    client = client_for(clerk)
    proof = upload(
        client,
        "bank_proof",
        {"customer_id": commerce.customer.pk, "invoice_id": invoice.pk, "payment_id": payment.pk},
    )
    assert proof.status_code == 201, proof.json()
    vendor = save_vendor(commerce.admin, {"name": "Cloud Hosting Ltd", "currency": "BDT"})
    vendor_doc = upload(
        client,
        "vendor_invoice",
        {"vendor_id": vendor.pk, "document_date": "2026-09-15"},
        name="inv.png",
        content=image_bytes(),
        content_type="image/png",
    )
    assert vendor_doc.status_code == 201, vendor_doc.json()
    return {
        "invoice": invoice,
        "payment": payment,
        "client": client,
        "proof": proof.json(),
        "vendor_doc": vendor_doc.json(),
        "vendor": vendor,
    }


def test_client_tree_year_client_invoice(filed, commerce):
    tree = filed["client"].get(f"{URL}client-tree/").json()
    assert tree[0]["year"] == 2026
    client = tree[0]["clients"][0]
    assert client["name"] == "Acme Trading Ltd"
    folder = client["invoices"][0]
    assert folder["number"] == "INV-2026-0001"
    assert folder["kinds"] == {"invoice": 1, "receipt": 1, "bank_proof": 1}


def test_vendor_tree_year_month_vendor(filed):
    tree = filed["client"].get(f"{URL}vendor-tree/").json()
    assert tree[0]["months"][0]["month"] == 9
    assert tree[0]["months"][0]["vendors"][0] == {
        "id": filed["vendor"].pk,
        "name": "Cloud Hosting Ltd",
        "count": 1,
        "kinds": {"vendor_invoice": 1},
    }


def test_bank_proofs_are_hidden_without_evidence_permission(filed, client_for, user_with):
    reader = client_for(user_with("reader", "finance.view"))
    listing = reader.get(f"{URL}?area=client").json()
    kinds = {row["kind"] for row in listing["results"]}
    assert kinds == {"invoice", "receipt"}
    tree = reader.get(f"{URL}client-tree/").json()
    assert tree[0]["clients"][0]["invoices"][0]["kinds"] == {"invoice": 1, "receipt": 1}
    assert reader.get(filed["proof"]["url"]).status_code == 404
    assert reader.get(f"{URL}{filed['proof']['id']}/").status_code == 404
    vendor_only = client_for(user_with("vendors", "documents.vendor.view"))
    assert vendor_only.get(f"{URL}?area=client").json()["count"] == 0
    assert vendor_only.get(filed["vendor_doc"]["url"]).status_code == 200
    invoice_pdf = FiledDocument.objects.get(kind="invoice")
    assert vendor_only.get(f"/api/v1/files/{invoice_pdf.file_id}/content/").status_code == 404
    nobody = client_for(user_with("nobody", "sales.manage"))
    assert nobody.get(f"{URL}").status_code == 403


def test_streaming_headers_and_proof_view_audit(filed):
    response = filed["client"].get(filed["proof"]["url"])
    assert response.status_code == 200 and response["Content-Type"] == "application/pdf"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Cache-Control"] == "private, no-store"
    assert "frame-ancestors 'self'" in response["Content-Security-Policy"]
    assert AuditEvent.objects.filter(action="documents.bank_proof_viewed").count() == 1
    download = filed["client"].get(filed["proof"]["download_url"])
    assert download["Content-Disposition"].startswith("attachment")


@pytest.mark.parametrize(
    ("name", "content", "content_type"),
    [
        ("script.pdf", "js", "application/pdf"),
        ("locked.pdf", "encrypted", "application/pdf"),
        ("page.html", b"<html><script>alert(1)</script></html>", "text/html"),
        ("fake.pdf", b"%PDF-1.7 not really", "application/pdf"),
        ("drawing.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"),
    ],
)
def test_unsafe_uploads_are_rejected(filed, commerce, name, content, content_type):
    body = (
        pdf_bytes(js=True)
        if content == "js"
        else pdf_bytes(password="pw")
        if content == "encrypted"
        else content
    )
    response = upload(
        filed["client"],
        "client_supporting",
        {"customer_id": commerce.customer.pk},
        name=name,
        content=body,
        content_type=content_type,
    )
    assert response.status_code == 400, response.json()


def test_image_polyglot_payload_is_stripped(filed, commerce):
    polyglot = image_bytes() + b"<script>alert(1)</script>"
    response = upload(
        filed["client"],
        "client_supporting",
        {"customer_id": commerce.customer.pk},
        name="scan.png",
        content=polyglot,
        content_type="image/png",
    )
    assert response.status_code == 201
    stored = filed["client"].get(response.json()["url"]).getvalue()
    assert b"<script>" not in stored


def test_oversize_upload_rejected(filed, commerce):
    big = b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 1)
    response = upload(
        filed["client"], "client_supporting", {"customer_id": commerce.customer.pk}, content=big
    )
    assert response.status_code == 400


def test_bank_proof_upload_requires_evidence_permission(filed, commerce, client_for, user_with):
    filer = client_for(user_with("filer2", "finance.view", "documents.manage"))
    response = upload(filer, "bank_proof", {"customer_id": commerce.customer.pk})
    assert response.status_code == 403


def test_links_must_belong_to_the_filed_party(filed, commerce):
    from apps.sales.services import save_customer

    other = save_customer(commerce.admin, {"name": "Other Client", "currency": "BDT"})
    response = upload(
        filed["client"],
        "client_supporting",
        {"customer_id": other.pk, "invoice_id": filed["invoice"].pk},
    )
    assert response.status_code == 400


def test_retention_generated_immutable_uploads_archived_with_reason(filed):
    client = filed["client"]
    generated = FiledDocument.objects.get(kind="invoice")
    assert (
        client.post(f"{URL}{generated.pk}/archive/", {"reason": "x"}, format="json").status_code
        == 409
    )
    proof = filed["proof"]["id"]
    assert client.post(f"{URL}{proof}/archive/", {"reason": ""}, format="json").status_code == 400
    archived = client.post(
        f"{URL}{proof}/archive/", {"reason": "Uploaded twice"}, format="json"
    ).json()
    assert archived["is_archived"] and archived["archived_reason"] == "Uploaded twice"
    assert proof not in [d["id"] for d in client.get(f"{URL}?area=client").json()["results"]]
    assert proof in [d["id"] for d in client.get(f"{URL}?area=client&archived=1").json()["results"]]
    with pytest.raises(IntegrityError), transaction.atomic():
        FiledDocument.objects.filter(pk=proof).delete()
    with pytest.raises(IntegrityError), transaction.atomic():
        FiledDocument.objects.filter(pk=generated.pk).update(title="Edited")


def test_refile_moves_upload_between_folders(filed, commerce):
    client = filed["client"]
    second = issued(commerce)
    response = client.patch(
        f"{URL}{filed['proof']['id']}/", {"invoice_id": second.pk}, format="json"
    )
    assert response.status_code == 200 and response.json()["invoice_number"] == second.number
    assert AuditEvent.objects.filter(action="documents.refiled").exists()
