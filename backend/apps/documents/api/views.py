from django.db.models import Count
from django.db.models.functions import ExtractMonth, ExtractYear
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import IsActiveUser, requires_any
from apps.files.api.serializers import file_url
from apps.sales.api.base import DomainViewSet, search, sort, validated

from .. import services
from ..models import FiledDocument
from ..selectors import client_invoice_filter, client_tree_rows, client_year_filter, number

READ = requires_any("finance.view", "documents.client.view", "documents.vendor.view")


class DocumentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    content_type = serializers.CharField(source="file.content_type")
    size = serializers.IntegerField(source="file.size")
    file_name = serializers.CharField(source="file.original_name")
    sha256 = serializers.CharField(source="file.sha256")
    customer_name = serializers.CharField(source="customer.name", default=None)
    vendor_name = serializers.CharField(source="vendor.name", default=None)
    invoice_number = serializers.CharField(source="invoice.number", default=None)
    payment_number = serializers.CharField(source="payment.number", default=None)
    bill_number = serializers.CharField(source="vendor_bill.number", default=None)
    expense_number = serializers.CharField(source="expense.number", default=None)
    uploaded_by = serializers.CharField(source="uploaded_by.display_name", default=None)

    class Meta:
        model = FiledDocument
        fields = [
            "id",
            "area",
            "kind",
            "title",
            "document_date",
            "generated",
            "restricted",
            "customer_id",
            "customer_name",
            "vendor_id",
            "vendor_name",
            "invoice_id",
            "invoice_number",
            "payment_id",
            "payment_number",
            "receipt_id",
            "credit_note_id",
            "vendor_bill_id",
            "bill_number",
            "expense_id",
            "expense_number",
            "vendor_payment_id",
            "notes",
            "is_archived",
            "archived_reason",
            "archived_at",
            "uploaded_by",
            "created_at",
            "content_type",
            "size",
            "file_name",
            "sha256",
            "url",
            "download_url",
        ]

    def get_url(self, obj) -> str:
        return file_url(obj.file)

    def get_download_url(self, obj) -> str:
        return f"{file_url(obj.file)}?download=1"


class UploadInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=list(services.UPLOAD_PURPOSES))
    file = serializers.FileField()
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    document_date = serializers.DateField(required=False)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    customer_id = serializers.IntegerField(required=False)
    vendor_id = serializers.IntegerField(required=False)
    invoice_id = serializers.IntegerField(required=False)
    payment_id = serializers.IntegerField(required=False)
    vendor_bill_id = serializers.IntegerField(required=False)
    expense_id = serializers.IntegerField(required=False)
    vendor_payment_id = serializers.IntegerField(required=False)


class RefileInput(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    document_date = serializers.DateField(required=False)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    customer_id = serializers.IntegerField(required=False)
    vendor_id = serializers.IntegerField(required=False)
    invoice_id = serializers.IntegerField(required=False, allow_null=True)
    payment_id = serializers.IntegerField(required=False, allow_null=True)
    vendor_bill_id = serializers.IntegerField(required=False, allow_null=True)
    expense_id = serializers.IntegerField(required=False, allow_null=True)
    vendor_payment_id = serializers.IntegerField(required=False, allow_null=True)


class ArchiveInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


@extend_schema(tags=["documents"])
class DocumentViewSet(DomainViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [IsActiveUser, READ]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    write_permissions = ("documents.manage",)

    def get_queryset(self):
        return services.visible(self.request.user).select_related(
            "file",
            "customer",
            "vendor",
            "invoice",
            "payment",
            "vendor_bill",
            "expense",
            "uploaded_by",
        )

    def get_object(self):
        doc = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if doc is None:
            raise NotFound()
        return doc

    def list(self, request):
        qs = search(
            self.get_queryset(), request, "title", "file__original_name", "invoice__number", "notes"
        )
        params = request.query_params
        invoice_id = number(params, "invoice")
        year = number(params, "year")
        area = params.get("area")
        for param, field in (
            ("area", "area"),
            ("kind", "kind"),
            ("customer", "customer_id"),
            ("vendor", "vendor_id"),
            ("payment", "payment_id"),
            ("bill", "vendor_bill_id"),
            ("expense", "expense_id"),
            ("month", "document_date__month"),
            ("vendor_payment", "vendor_payment_id"),
        ):
            if params.get(param):
                value = params[param] if param in ("area", "kind") else number(params, param)
                qs = qs.filter(**{field: value})
        if invoice_id:
            qs = qs.filter(client_invoice_filter(invoice_id))
        if year:
            if invoice_id:
                from apps.billing.models import Invoice

                if not Invoice.objects.filter(pk=invoice_id, issue_date__year=year).exists():
                    qs = qs.none()
            elif area == "vendor":
                qs = qs.filter(document_date__year=year)
            elif area == "client":
                qs = qs.filter(client_year_filter(year))
            else:
                from django.db.models import Q

                qs = qs.filter(
                    Q(area="vendor", document_date__year=year)
                    | (Q(area="client") & client_year_filter(year))
                )
        if params.get("unlinked") == "1":
            qs = qs.filter(invoice__isnull=True, vendor_bill__isnull=True, expense__isnull=True)
            if area == "client":
                qs = qs.filter(payment__allocations__isnull=True)
        if params.get("archived") != "1":
            qs = qs.exclude(is_archived=True)
        return self.respond_list(
            sort(qs.distinct(), request, ("document_date", "title", "created_at"), "-document_date")
        )

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=UploadInput)
    def create(self, request):
        data = validated(UploadInput, request.data)
        file = data.pop("file")
        return Response(
            self.serializer_class(services.upload(request, data, file)).data, status=201
        )

    @extend_schema(request=RefileInput)
    def partial_update(self, request, pk=None):
        data = validated(RefileInput, request.data, partial=True)
        return Response(self.serializer_class(services.refile(request, pk, data)).data)

    @extend_schema(request=ArchiveInput)
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        reason = validated(ArchiveInput, request.data)["reason"]
        return Response(self.serializer_class(services.archive(request, pk, reason)).data)


@extend_schema(
    tags=["documents"],
    responses=inline_serializer(
        "ClientTreeYear",
        {
            "year": serializers.IntegerField(),
            "count": serializers.IntegerField(),
            "clients": serializers.ListField(child=serializers.DictField()),
        },
        many=True,
    ),
)
class ClientTreeView(APIView):
    """Year → client → invoice folders with document counts (derived, never stored)."""

    permission_classes = [IsActiveUser, READ]

    def get(self, request):
        qs = client_tree_rows(request.user)
        years = {}
        year_seen, client_seen = set(), set()
        for row in qs:
            year = years.setdefault(row["year"], {"year": row["year"], "count": 0, "clients": {}})
            client = year["clients"].setdefault(
                row["customer_id"],
                {
                    "id": row["customer_id"],
                    "name": row["customer__name"],
                    "count": 0,
                    "invoices": {},
                    "other": {},
                },
            )
            target = (
                client["invoices"].setdefault(
                    row["invoice_id"],
                    {
                        "id": row["invoice_id"],
                        "number": row["invoice__number"],
                        "count": 0,
                        "kinds": {},
                    },
                )
                if row["invoice_id"]
                else None
            )
            if target is None:
                client["other"][row["kind"]] = client["other"].get(row["kind"], 0) + row["n"]
            else:
                target["kinds"][row["kind"]] = target["kinds"].get(row["kind"], 0) + row["n"]
                target["count"] += row["n"]
            year_key = (row["year"], row["document_id"])
            client_key = (row["year"], row["customer_id"], row["document_id"])
            if client_key not in client_seen:
                client["count"] += row["n"]
                client_seen.add(client_key)
            if year_key not in year_seen:
                year["count"] += row["n"]
                year_seen.add(year_key)
        out = []
        for year in sorted(years.values(), key=lambda y: -y["year"]):
            clients = []
            for client in sorted(year["clients"].values(), key=lambda c: c["name"].lower()):
                client["invoices"] = sorted(
                    client["invoices"].values(), key=lambda i: i["number"] or "", reverse=True
                )
                clients.append(client)
            out.append({**year, "clients": clients})
        return Response(out)


@extend_schema(
    tags=["documents"],
    responses=inline_serializer(
        "VendorTreeYear",
        {
            "year": serializers.IntegerField(),
            "count": serializers.IntegerField(),
            "months": serializers.ListField(child=serializers.DictField()),
        },
        many=True,
    ),
)
class VendorTreeView(APIView):
    """Year → month → vendor folders with document counts."""

    permission_classes = [IsActiveUser, READ]

    def get(self, request):
        qs = (
            services.visible(request.user)
            .filter(area="vendor", is_archived=False)
            .annotate(year=ExtractYear("document_date"), month=ExtractMonth("document_date"))
            .values("year", "month", "vendor_id", "vendor__name", "kind")
            .annotate(n=Count("id"))
            .order_by()
        )
        years = {}
        for row in qs:
            year = years.setdefault(row["year"], {"year": row["year"], "count": 0, "months": {}})
            month = year["months"].setdefault(
                row["month"], {"month": row["month"], "count": 0, "vendors": {}}
            )
            vendor = month["vendors"].setdefault(
                row["vendor_id"],
                {"id": row["vendor_id"], "name": row["vendor__name"], "count": 0, "kinds": {}},
            )
            vendor["kinds"][row["kind"]] = vendor["kinds"].get(row["kind"], 0) + row["n"]
            for node in (vendor, month, year):
                node["count"] += row["n"]
        out = []
        for year in sorted(years.values(), key=lambda y: -y["year"]):
            months = []
            for month in sorted(year["months"].values(), key=lambda m: -m["month"]):
                month["vendors"] = sorted(
                    month["vendors"].values(), key=lambda v: v["name"].lower()
                )
                months.append(month)
            out.append({**year, "months": months})
        return Response(out)
