"""Bounded cross-module search with per-record permission enforcement.

Only purpose-built searchable fields are exposed, no private document payload
or unrestricted file metadata is returned.
"""
from django.db.models import Q

from apps.accounts.authorization import get_permission_codes
from apps.billing.models import Invoice
from apps.documents.models import FiledDocument
from apps.purchasing.models import Vendor, VendorBill
from apps.sales.models import Customer


def global_results(user, term: str) -> list[dict[str, str]]:
    q = term.strip()
    if len(q) < 2:
        return []

    codes = get_permission_codes(user)
    result: list[dict[str, str]] = []

    def add(category: str, title: str, description: str, href: str):
        result.append({
            "category": category,
            "title": title,
            "description": description,
            "href": href,
        })

    if "finance.view" in codes:
        for customer in Customer.objects.filter(
            Q(name__icontains=q) | Q(code__icontains=q) | Q(email__icontains=q)
        ).order_by("name")[:6]:
            add("Customers", customer.name, customer.code, f"/sales/customers/{customer.pk}")

        for invoice in Invoice.objects.filter(
            Q(number__icontains=q) | Q(reference__icontains=q)
            | Q(customer__name__icontains=q)
        ).select_related("customer").order_by("-pk")[:6]:
            add("Invoices", invoice.number or invoice.reference or "Draft invoice",
                invoice.customer.name, "/sales/invoices")

        for vendor in Vendor.objects.filter(
            Q(name__icontains=q) | Q(code__icontains=q) | Q(email__icontains=q)
        ).order_by("name")[:6]:
            add("Suppliers", vendor.name, vendor.code, "/purchases/vendors")

        for bill in VendorBill.objects.filter(
            Q(number__icontains=q) | Q(vendor_reference__icontains=q)
            | Q(vendor__name__icontains=q)
        ).select_related("vendor").order_by("-pk")[:6]:
            add("Vendor bills", bill.number or bill.vendor_reference or "Draft vendor bill",
                bill.vendor.name, "/purchases/bills")

    for area, permission, href in [
        ("client", "documents.client.view", "/client-documents"),
        ("vendor", "documents.vendor.view", "/vendor-documents"),
    ]:
        if permission not in codes:
            continue
        documents = FiledDocument.objects.filter(area=area, is_archived=False).filter(
            Q(title__icontains=q) | Q(notes__icontains=q)
        )
        if "banking.evidence.view" not in codes:
            documents = documents.filter(restricted=False)
        for document in documents.order_by("-document_date", "-pk")[:6]:
            add("Client documents" if area == "client" else "Vendor documents",
                document.title, str(document.document_date), href)

    return result[:35]
