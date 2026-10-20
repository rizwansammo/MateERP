"""Exercise every official layout, including its retained PDF and extracted business content."""

import io
import os
from pathlib import Path

import pytest
from pypdf import PdfReader

from apps.billing.services import credits
from apps.billing.tests.conftest import DAY, as_user, issued
from apps.billing.tests.test_payments import record, verify
from apps.branding.services import get_draft, publish, save_draft
from apps.documents.services import generate_pdf
from apps.files.services import private_storage

pytestmark = pytest.mark.django_db


def rendered(obj, name):
    assert obj.pdf_status == "ready", obj.pdf_error
    with private_storage().open(obj.pdf_file.storage_name, "rb") as source:
        data = source.read()
    pdf = PdfReader(io.BytesIO(data))
    assert len(pdf.pages) == 1
    assert abs(pdf.pages[0].mediabox.width - 595.28) < 1
    text = pdf.pages[0].extract_text()
    assert "Acme Trading Ltd" in text
    assert obj.number in text
    assert "11,000.00" in text
    assert "PREVIEW" not in text
    # Optional retained visual evidence, never written in a normal CI run.
    directory = os.environ.get("MATEERP_PDF_REVIEW_DIR")
    if directory:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{name}.pdf").write_bytes(data)


@pytest.mark.parametrize("template", ["meridian", "ledger", "atlas"])
@pytest.mark.parametrize("kind", ["invoice", "credit_note"])
def test_invoice_and_credit_layouts(commerce, template, kind):
    config = {**get_draft().config, "invoice_template": template}
    save_draft(commerce.admin, config)
    publish(commerce.admin, label=f"{template} official layout")
    invoice = issued(commerce)
    obj = invoice
    if kind == "credit_note":
        obj = credits.request_credit_note(
            as_user(commerce.users.crediter),
            invoice.pk,
            {"full": True, "issue_date": DAY, "reason": "Service cancellation"},
            f"pdf-{kind}-{template}",
        )
    obj = generate_pdf(kind, obj.pk)
    rendered(obj, f"{kind}-{template}")


@pytest.mark.parametrize("template", ["official", "compact"])
def test_money_receipt_layouts(commerce, template):
    config = {**get_draft().config, "receipt_template": template}
    save_draft(commerce.admin, config)
    publish(commerce.admin, label=f"{template} receipt")
    invoice = issued(commerce)
    payment = verify(commerce, record(commerce, invoice, "11000", f"receipt-{template}"))
    receipt = generate_pdf("receipt", payment.receipt.pk)
    rendered(receipt, f"receipt-{template}")


@pytest.mark.parametrize("template", ["meridian", "ledger", "atlas"])
def test_multi_page_invoice_keeps_every_line_and_final_totals(commerce, template):
    save_draft(commerce.admin, {**get_draft().config, "invoice_template": template})
    publish(commerce.admin, label=f"{template} multi-page")
    invoice = issued(
        commerce,
        lines=[
            {
                "description": f"Service line {i:03d} with a detailed delivery reference",
                "unit_price": "100",
                "revenue_account_id": commerce.books.accounts["4100"].pk,
            }
            for i in range(1, 91)
        ],
    )
    invoice = generate_pdf("invoice", invoice.pk)
    assert invoice.pdf_status == "ready", invoice.pdf_error
    with private_storage().open(invoice.pdf_file.storage_name, "rb") as source:
        data = source.read()
    pdf = PdfReader(io.BytesIO(data))
    assert len(pdf.pages) >= 3
    text = "\n".join(page.extract_text() for page in pdf.pages)
    for i in range(1, 91):
        assert f"Service line {i:03d}" in text
    assert "9,000.00" in pdf.pages[-1].extract_text()
    directory = os.environ.get("MATEERP_PDF_REVIEW_DIR")
    if directory:
        (Path(directory) / f"invoice-{template}-multi.pdf").write_bytes(data)
