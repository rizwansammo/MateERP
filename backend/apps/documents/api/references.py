"""Bounded identity-only choices for authorized document filing, without financial amounts."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import IsActiveUser, get_permission_codes, requires
from apps.billing.models import CustomerPayment, Invoice
from apps.purchasing.models import Expense, Vendor, VendorBill, VendorPayment
from apps.sales.models import Customer

from ..selectors import number


def choices(qs, label, selected=None):
    rows = list(qs.order_by("-pk")[:100])
    if selected and all(row.pk != selected for row in rows):
        extra = qs.filter(pk=selected).first()
        if extra:
            rows.insert(0, extra)
    return [{"value": str(row.pk), "label": label(row)} for row in rows]


@extend_schema(tags=["documents"], responses=OpenApiTypes.OBJECT)
class FilingReferencesView(APIView):
    permission_classes = [IsActiveUser, requires("documents.manage")]

    def get(self, request):
        area = request.query_params.get("area")
        if area not in ("client", "vendor"):
            raise ValidationError({"area": "Choose client or vendor."})
        codes = get_permission_codes(request.user)
        if "finance.view" not in codes and f"documents.{area}.view" not in codes:
            raise PermissionDenied()
        party_id = number(request.query_params, "party")
        q = request.query_params.get("search", "")[:100]
        model = Customer if area == "client" else Vendor
        parties = model.objects.filter(name__icontains=q)
        out = {"parties": choices(parties, lambda p: f"{p.code} · {p.name}", party_id)}
        models = (
            {"invoice_id": Invoice, "payment_id": CustomerPayment}
            if area == "client"
            else {
                "vendor_bill_id": VendorBill,
                "expense_id": Expense,
                "vendor_payment_id": VendorPayment,
            }
        )
        party_field = "customer_id" if area == "client" else "vendor_id"
        for key, target in models.items():
            qs = target.objects.filter(**{party_field: party_id})
            out[key] = choices(
                qs,
                lambda record: record.number or f"Draft · {record.pk}",
                number(request.query_params, key),
            )
        return Response(out)
