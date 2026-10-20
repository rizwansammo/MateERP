"""Filing, generation state machine, uploads and access policy for client/vendor documents.

PDF generation runs after the issuing transaction has committed:

    pending ──render──▶ ready      (file stored, filed and linked in one transaction)
       └────error────▶ failed ──retry──▶ ready

A ready PDF is never regenerated (database trigger). Rendering happens outside any
financial lock; the final link step locks only the document row and re-checks state,
so concurrent retries cannot produce two official PDFs. A file written before a
failed link step is deleted again; ``documents_orphans`` reports anything left over.
"""

import logging

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.authorization import get_permission_codes, require
from apps.audit.services import record
from apps.core.exceptions import BusinessRuleViolation
from apps.files.access import register_purpose_policy
from apps.files.models import FilePurpose
from apps.files.services import private_storage, store_document, store_generated_pdf

from .models import FiledDocument
from .rendering import invoice_context, receipt_context, render_pdf

log = logging.getLogger(__name__)
Kind = FiledDocument.Kind

UPLOAD_PURPOSES = {
    Kind.BANK_PROOF: FilePurpose.BANK_PROOF,
    Kind.CLIENT_SUPPORTING: FilePurpose.CLIENT_DOCUMENT,
    Kind.VENDOR_INVOICE: FilePurpose.VENDOR_DOCUMENT,
    Kind.VENDOR_RECEIPT: FilePurpose.VENDOR_DOCUMENT,
    Kind.VENDOR_SUPPORTING: FilePurpose.VENDOR_DOCUMENT,
}
CLIENT_READ = {"finance.view", "documents.client.view"}
VENDOR_READ = {"finance.view", "documents.vendor.view"}


# ---------------------------------------------------------------- access policy


def can_view(user, doc: FiledDocument) -> bool:
    perms = get_permission_codes(user)
    if doc.is_archived and "documents.manage" not in perms:
        return False
    if doc.area == FiledDocument.Area.VENDOR:
        return bool(VENDOR_READ & perms)
    if doc.restricted and "banking.evidence.view" not in perms:
        return False
    return bool(CLIENT_READ & perms)


def visible(user, qs=None):
    """Documents the user may list; restricted proofs disappear entirely without access."""
    perms = get_permission_codes(user)
    qs = FiledDocument.objects.all() if qs is None else qs
    areas = [a for a, read in (("client", CLIENT_READ), ("vendor", VENDOR_READ)) if read & perms]
    qs = qs.filter(area__in=areas)
    if "banking.evidence.view" not in perms:
        qs = qs.exclude(restricted=True)
    if "documents.manage" not in perms:
        qs = qs.exclude(is_archived=True)
    return qs


def _file_policy(user, stored) -> bool:
    doc = FiledDocument.objects.filter(file=stored).first()
    return doc is not None and can_view(user, doc)


for _purpose in (
    FilePurpose.INVOICE_PDF,
    FilePurpose.RECEIPT_PDF,
    FilePurpose.CREDIT_NOTE_PDF,
    FilePurpose.BANK_PROOF,
    FilePurpose.CLIENT_DOCUMENT,
    FilePurpose.VENDOR_DOCUMENT,
):
    register_purpose_policy(_purpose, _file_policy)


# ---------------------------------------------------------------- generated PDFs


def _spec(kind):
    from apps.billing.models import CreditNote, Invoice, MoneyReceipt

    return {
        "invoice": (Invoice, FilePurpose.INVOICE_PDF, Kind.INVOICE),
        "receipt": (MoneyReceipt, FilePurpose.RECEIPT_PDF, Kind.RECEIPT),
        "credit_note": (CreditNote, FilePurpose.CREDIT_NOTE_PDF, Kind.CREDIT_NOTE),
    }[kind]


def _render(kind, obj) -> bytes:
    if kind == "invoice":
        return render_pdf(
            "documents/invoice.html", invoice_context(obj.snapshot, obj.branding_version)
        )
    if kind == "receipt":
        return render_pdf(
            "documents/receipt.html", receipt_context(obj.snapshot, obj.branding_version)
        )
    return render_pdf(
        "documents/invoice.html", invoice_context(obj.snapshot, obj.branding_version, credit=True)
    )


def _filing(kind, obj) -> dict:
    if kind == "invoice":
        return {
            "title": f"Invoice {obj.number}",
            "document_date": obj.issue_date,
            "customer_id": obj.customer_id,
            "invoice_id": obj.pk,
        }
    if kind == "receipt":
        first = obj.payment.allocations.order_by("pk").first()
        return {
            "title": f"Money receipt {obj.number}",
            "document_date": obj.issue_date,
            "customer_id": obj.payment.customer_id,
            "invoice_id": first.invoice_id if first else None,
            "payment_id": obj.payment_id,
            "receipt_id": obj.pk,
        }
    return {
        "title": f"Credit note {obj.number}",
        "document_date": obj.issue_date,
        "customer_id": obj.customer_id,
        "invoice_id": obj.invoice_id,
        "credit_note_id": obj.pk,
    }


def generate_pdf(kind: str, pk) -> object:
    """Render and file the official PDF for an issued document (idempotent)."""
    model, purpose, filed_kind = _spec(kind)
    obj = model.objects.select_related("branding_version").get(pk=pk)
    if obj.pdf_status == "ready" or not obj.number:
        return obj
    try:
        data = _render(kind, obj)
    except Exception as exc:  # noqa: BLE001 — any renderer failure becomes a retryable state
        log.exception("PDF generation failed for %s %s", kind, pk)
        with transaction.atomic():
            current = model.objects.select_for_update().get(pk=pk)
            if current.pdf_status != "ready":
                current.pdf_status = "failed"
                current.pdf_error = f"{type(exc).__name__}: rendering failed"[:300]
                current.save(update_fields=["pdf_status", "pdf_error"])
        return model.objects.get(pk=pk)
    stored = None
    try:
        with transaction.atomic():
            current = model.objects.select_for_update().get(pk=pk)
            if current.pdf_status == "ready":
                return current
            stored = store_generated_pdf(
                data, purpose=purpose, name=f"{current.number}.pdf", user=None
            )
            FiledDocument.objects.create(
                area=FiledDocument.Area.CLIENT,
                kind=filed_kind,
                file=stored,
                generated=True,
                **_filing(kind, current),
            )
            current.pdf_file = stored
            current.pdf_status = "ready"
            current.pdf_error = ""
            current.save(update_fields=["pdf_file", "pdf_status", "pdf_error"])
            return current
    except Exception:
        if stored is not None:
            private_storage().delete(stored.storage_name)
        raise


def retry_pdf(request, kind: str, pk):
    """User-triggered retry for a failed or missing official PDF."""
    model, _, _ = _spec(kind)
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        raise NotFound()
    perms = get_permission_codes(request.user)
    if (
        not {"invoices.issue", "payments.approve", "credit_notes.manage", "documents.manage"}
        & perms
    ):
        raise PermissionDenied()
    if not obj.number:
        raise BusinessRuleViolation("Only issued documents have an official PDF.")
    if obj.pdf_status != "ready":
        obj = generate_pdf(kind, pk)
        record(
            f"documents.{kind}_pdf_retried",
            request=request,
            target=obj,
            after={"status": obj.pdf_status},
        )
    return obj


def generate_pending(limit=200) -> dict:
    """Retry every issued document whose PDF is pending or failed (management command)."""
    from apps.billing.models import CreditNote, Invoice, MoneyReceipt

    result = {}
    for kind, model in (
        ("invoice", Invoice),
        ("receipt", MoneyReceipt),
        ("credit_note", CreditNote),
    ):
        done = failed = 0
        ids = (
            model.objects.filter(number__isnull=False)
            .exclude(pdf_status="ready")
            .values_list("pk", flat=True)[:limit]
        )
        for pk in ids:
            obj = generate_pdf(kind, pk)
            done, failed = (done + 1, failed) if obj.pdf_status == "ready" else (done, failed + 1)
        result[kind] = {"ready": done, "failed": failed}
    return result


# ---------------------------------------------------------------- uploads


def _links(area, data):
    """Resolve optional business links and check they belong to the filed party."""
    from apps.billing.models import CustomerPayment, Invoice
    from apps.purchasing.models import Expense, Vendor, VendorBill, VendorPayment
    from apps.sales.models import Customer

    out = {}
    if area == FiledDocument.Area.CLIENT:
        customer = Customer.objects.filter(pk=data.get("customer_id")).first()
        if customer is None:
            raise ValidationError({"customer_id": "Choose the client this document belongs to."})
        out["customer"] = customer
        for key, model in (("invoice_id", Invoice), ("payment_id", CustomerPayment)):
            if data.get(key):
                obj = model.objects.filter(pk=data[key], customer=customer).first()
                if obj is None:
                    raise ValidationError({key: "The linked record belongs to another client."})
                out[key.removesuffix("_id")] = obj
    else:
        vendor = Vendor.objects.filter(pk=data.get("vendor_id")).first()
        if vendor is None:
            raise ValidationError({"vendor_id": "Choose the vendor this document belongs to."})
        out["vendor"] = vendor
        for key, model in (
            ("vendor_bill_id", VendorBill),
            ("expense_id", Expense),
            ("vendor_payment_id", VendorPayment),
        ):
            if data.get(key):
                obj = model.objects.filter(pk=data[key], vendor=vendor).first()
                if obj is None:
                    raise ValidationError({key: "The linked record belongs to another vendor."})
                out[key.removesuffix("_id")] = obj
    return out


def _require_kind(user, kind):
    require(user, "documents.manage")
    if kind == Kind.BANK_PROOF:
        require(user, "banking.evidence.view")


@transaction.atomic
def upload(request, data, file):
    kind = data.get("kind")
    if kind not in UPLOAD_PURPOSES:
        raise ValidationError({"kind": "Choose an uploadable document type."})
    _require_kind(request.user, kind)
    area = (
        FiledDocument.Area.CLIENT
        if kind in FiledDocument.CLIENT_KINDS
        else FiledDocument.Area.VENDOR
    )
    links = _links(area, data)
    if file is None:
        raise ValidationError({"file": "Attach a PDF, PNG, JPEG or WEBP file."})
    stored = store_document(file, purpose=UPLOAD_PURPOSES[kind], user=request.user)
    doc = FiledDocument.objects.create(
        area=area,
        kind=kind,
        file=stored,
        title=(data.get("title") or stored.original_name)[:200],
        document_date=data.get("document_date") or timezone.localdate(),
        restricted=kind == Kind.BANK_PROOF,
        notes=(data.get("notes") or "")[:500],
        uploaded_by=request.user,
        **links,
    )
    record(
        "documents.uploaded",
        request=request,
        target=doc,
        after={"kind": kind, "area": area, "sha256": stored.sha256, "size": stored.size},
    )
    return doc


def _editable(request, pk):
    doc = FiledDocument.objects.select_for_update().filter(pk=pk).first()
    if doc is None or not can_view(request.user, doc):
        raise NotFound()
    _require_kind(request.user, doc.kind)
    if doc.generated:
        raise BusinessRuleViolation(
            "System-generated invoices, receipts and credit notes are immutable.",
            code="generated_document",
        )
    return doc


@transaction.atomic
def refile(request, pk, data):
    doc = _editable(request, pk)
    if doc.is_archived:
        raise BusinessRuleViolation("Restore is not available; archived documents stay archived.")
    before = {"title": doc.title, "document_date": doc.document_date, "notes": doc.notes}
    links = _links(doc.area, {**_current_links(doc), **data})
    for key in (
        "customer",
        "vendor",
        "invoice",
        "payment",
        "vendor_bill",
        "expense",
        "vendor_payment",
    ):
        setattr(doc, key, links.get(key))
    for key in ("title", "document_date", "notes"):
        if key in data and data[key] not in (None, ""):
            setattr(doc, key, data[key])
    doc.save()
    record("documents.refiled", request=request, target=doc, before=before, after=data)
    return doc


def _current_links(doc):
    return {
        f"{key}_id": getattr(doc, f"{key}_id")
        for key in (
            "customer",
            "vendor",
            "invoice",
            "payment",
            "vendor_bill",
            "expense",
            "vendor_payment",
        )
    }


@transaction.atomic
def archive(request, pk, reason):
    doc = _editable(request, pk)
    if not reason.strip():
        raise ValidationError({"reason": "Explain why the document is archived."})
    if doc.is_archived:
        return doc
    doc.is_archived = True
    doc.archived_reason = reason.strip()[:500]
    doc.archived_by = request.user
    doc.archived_at = timezone.now()
    doc.save()
    record("documents.archived", request=request, target=doc, reason=doc.archived_reason)
    return doc
