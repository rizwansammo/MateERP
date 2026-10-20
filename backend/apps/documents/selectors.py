"""Virtual invoice bundles reference one retained file across every settled invoice."""

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from . import services


def number(params, key):
    value = params.get(key)
    if not value:
        return None
    try:
        result = int(value)
        if result < 1:
            raise ValueError
        return result
    except (TypeError, ValueError) as exc:
        raise ValidationError({key: "Enter a positive integer."}) from exc


def client_invoice_filter(invoice_id):
    return (
        Q(invoice_id=invoice_id)
        | Q(kind="receipt", payment__allocations__invoice_id=invoice_id)
        | Q(invoice__isnull=True, payment__allocations__invoice_id=invoice_id)
    )


def client_year_filter(year):
    return (
        Q(invoice__issue_date__year=year)
        | Q(kind="receipt", payment__allocations__invoice__issue_date__year=year)
        | Q(invoice__isnull=True, payment__allocations__invoice__issue_date__year=year)
        | Q(invoice__isnull=True, payment__allocations__isnull=True, document_date__year=year)
    )


def client_tree_rows(user):
    docs = (
        services.visible(user)
        .filter(area="client", is_archived=False)
        .select_related("customer", "invoice", "payment")
        .prefetch_related("payment__allocations__invoice")
    )
    for doc in docs:
        invoices = []
        if doc.payment_id and (doc.kind == "receipt" or not doc.invoice_id):
            invoices = [a.invoice for a in doc.payment.allocations.all()]
        if not invoices and doc.invoice_id:
            invoices = [doc.invoice]
        for invoice in {i.pk: i for i in invoices}.values() if invoices else [None]:
            yield {
                "document_id": doc.pk,
                "year": invoice.issue_date.year if invoice else doc.document_date.year,
                "customer_id": doc.customer_id,
                "customer__name": doc.customer.name,
                "invoice_id": invoice.pk if invoice else None,
                "invoice__number": invoice.number if invoice else None,
                "kind": doc.kind,
                "n": 1,
            }
