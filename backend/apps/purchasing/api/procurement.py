from drf_spectacular.utils import extend_schema, extend_schema_serializer
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounting.api.serializers import DecimalText
from apps.accounting.money import ZERO, strings
from apps.accounts.authorization import require
from apps.sales.api.base import DomainViewSet, search, sort, validated

from ..models import (
    GoodsReceipt,
    ProcurementEvidence,
    PurchaseOrder,
    PurchaseOrderLine,
    ReceiptBillMatch,
    ReceiptCostCorrection,
    SupplierReturn,
)
from ..services import costing, returns
from ..services import procurement as services


@extend_schema_serializer(component_name="PurchaseOrderLine")
class LineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    received_quantity = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id",
            "position",
            "item_id",
            "item_name",
            "description",
            "quantity",
            "unit_price",
            "tax_code_id",
            "taxable",
            "tax",
            "total",
            "received_quantity",
        ]

    def get_received_quantity(self, obj) -> str:
        return str(sum((r.quantity for r in obj.receipts.all()), ZERO))


@extend_schema_serializer(component_name="PurchaseOrder")
class OrderSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    lines = LineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "number",
            "vendor_id",
            "vendor_name",
            "date",
            "expected_date",
            "currency",
            "prices_include_tax",
            "notes",
            "status",
            "revision",
            "taxable",
            "tax",
            "total",
            "approval_id",
            "revised_from_id",
            "created_by_id",
            "approved_by_id",
            "created_at",
            "issued_at",
            "closing_reason",
            "lines",
        ]


@extend_schema_serializer(component_name="PurchaseOrderLineInput")
class LineInput(serializers.Serializer):
    item_id = serializers.IntegerField()
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    quantity = DecimalText()
    unit_price = DecimalText()
    tax_code_id = serializers.IntegerField(required=False, allow_null=True)


@extend_schema_serializer(component_name="PurchaseOrderInput")
class OrderInput(serializers.Serializer):
    vendor_id = serializers.IntegerField(required=False)
    date = serializers.DateField()
    expected_date = serializers.DateField(required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, required=False)
    prices_include_tax = serializers.BooleanField(required=False)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    revision = serializers.IntegerField(required=False)
    lines = LineInput(many=True, allow_empty=False, max_length=250)


@extend_schema_serializer(component_name="PurchaseOrderAmendmentInput")
class AmendmentInput(OrderInput):
    reason = serializers.CharField(max_length=500)


@extend_schema_serializer(component_name="ProcurementEvidenceInput")
class EvidenceInput(serializers.Serializer):
    file = serializers.FileField()
    receipt_id = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(max_length=500)


@extend_schema_serializer(component_name="ProcurementEvidence")
class EvidenceSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="file.original_name")
    content_type = serializers.CharField(source="file.content_type")
    size = serializers.IntegerField(source="file.size")

    class Meta:
        model = ProcurementEvidence
        fields = [
            "id",
            "file_id",
            "receipt_id",
            "description",
            "name",
            "content_type",
            "size",
            "created_at",
        ]


@extend_schema_serializer(component_name="GoodsReceipt")
class ReceiptSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="order_line.item.name")
    order_number = serializers.CharField(source="order_line.order.number")

    class Meta:
        model = GoodsReceipt
        fields = [
            "id",
            "order_line_id",
            "order_number",
            "item_name",
            "date",
            "quantity",
            "rejected_quantity",
            "kind",
            "location_id",
            "reference",
            "reason",
            "evidence_id",
            "native_value",
            "base_value",
            "exchange_rate",
            "movement_id",
            "key",
            "created_by_id",
            "created_at",
        ]


class ReceiptInput(serializers.Serializer):
    order_line_id = serializers.IntegerField()
    date = serializers.DateField()
    quantity = DecimalText()
    rejected_quantity = DecimalText(required=False)
    location_id = serializers.IntegerField(required=False, allow_null=True)
    reference = serializers.CharField(max_length=100)
    reason = serializers.CharField(max_length=500)
    key = serializers.CharField(min_length=8, max_length=140)


class CostCorrectionInput(serializers.Serializer):
    date = serializers.DateField()
    new_net_cost = DecimalText()
    variance_account_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=1000)
    key = serializers.CharField(min_length=8, max_length=140)


class CostCorrectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptCostCorrection
        fields = [
            "id",
            "receipt_id",
            "date",
            "native_delta",
            "base_delta",
            "inventory_delta",
            "consumed_delta",
            "variance_account_id",
            "basis",
            "reason",
            "journal_id",
            "movement_id",
            "created_at",
        ]


class CostCorrectionResult(serializers.Serializer):
    status = serializers.CharField()
    correction_id = serializers.IntegerField(allow_null=True)
    approval_id = serializers.IntegerField(allow_null=True)


class ReceivingReconciliationSerializer(serializers.Serializer):
    received_base = DecimalText()
    corrections_base = DecimalText()
    returned_base = DecimalText()
    matched_base = DecimalText()
    unmatched_base = DecimalText()
    ledger = DecimalText()
    difference = DecimalText()


class SupplierReturnInput(serializers.Serializer):
    date = serializers.DateField()
    quantity = DecimalText()
    location_id = serializers.IntegerField(min_value=1)
    variance_account_id = serializers.IntegerField(min_value=1)
    reference = serializers.CharField(max_length=100)
    reason = serializers.CharField(max_length=500)
    key = serializers.CharField(min_length=8, max_length=140)


class SupplierReturnSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierReturn
        fields = [
            "id",
            "receipt_id",
            "date",
            "quantity",
            "native_value",
            "base_value",
            "inventory_value",
            "variance",
            "reference",
            "reason",
            "basis",
            "journal_id",
            "approval_id",
            "created_at",
        ]


class SupplierReturnResult(serializers.Serializer):
    status = serializers.CharField()
    return_id = serializers.IntegerField(allow_null=True)
    approval_id = serializers.IntegerField(allow_null=True)


@extend_schema_serializer(component_name="ProcurementReasonInput")
class ReasonInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, default="", allow_blank=True)


class MatchRow(serializers.Serializer):
    receipt_id = serializers.IntegerField()
    quantity = DecimalText()


@extend_schema_serializer(component_name="ReceiptBillMatchInput")
class MatchInput(serializers.Serializer):
    bill_line_id = serializers.IntegerField()
    receipts = MatchRow(many=True, max_length=250)


class MatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptBillMatch
        fields = ["id", "receipt_id", "bill_line_id", "quantity", "native_value", "base_value"]


@extend_schema(tags=["procurement"])
class OrderViewSet(DomainViewSet):
    queryset = PurchaseOrder.objects.select_related("vendor").prefetch_related(
        "lines__item", "lines__receipts"
    )
    serializer_class = OrderSerializer
    write_permissions = ("procurement.manage",)
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def list(self, request):
        qs = search(self.queryset, request, "number", "vendor__name", "notes")
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return self.respond_list(sort(qs, request, ("date", "number", "total"), "-date"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=OrderInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                services.save_order(request, validated(OrderInput, request.data))
            ).data,
            status=201,
        )

    @extend_schema(request=OrderInput)
    def partial_update(self, request, pk=None):
        return Response(
            self.serializer_class(
                services.save_order(request, validated(OrderInput, request.data), pk)
            ).data
        )

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return Response(self.serializer_class(services.submit_order(request, pk)).data)

    @extend_schema(request=AmendmentInput)
    @action(detail=True, methods=["post"])
    def amend(self, request, pk=None):
        data = validated(AmendmentInput, request.data)
        obj = services.amend_order(request, pk, data, data.pop("reason"))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=EvidenceInput, responses=EvidenceSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def evidence(self, request, pk=None):
        order = self.get_object()
        if request.method == "POST":
            data = validated(EvidenceInput, request.data)
            obj = services.add_evidence(request, order.pk, data, data.pop("file"))
            return Response(EvidenceSerializer(obj).data, status=201)
        require(request.user, "documents.vendor.view")
        return self.respond_list(
            order.evidence.select_related("file").order_by("-pk"), EvidenceSerializer
        )

    @extend_schema(request=ReasonInput, operation_id="purchasing_order_transition")
    @action(detail=True, methods=["post"], url_path=r"(?P<operation>issue|cancel|close)")
    def transition(self, request, pk=None, operation=None):
        data = validated(ReasonInput, request.data)
        return Response(
            self.serializer_class(services.transition(request, pk, operation, data["reason"])).data
        )


@extend_schema(tags=["procurement"])
class ReceiptViewSet(DomainViewSet):
    queryset = GoodsReceipt.objects.select_related("order_line__item", "order_line__order")
    serializer_class = ReceiptSerializer
    write_permissions = ("procurement.manage", "bills.manage")

    @extend_schema(request=SupplierReturnInput, responses=SupplierReturnResult, methods=["POST"])
    @extend_schema(responses=SupplierReturnSerializer(many=True), methods=["GET"])
    @action(detail=True, methods=["get", "post"], url_path="supplier-returns")
    def supplier_returns(self, request, pk=None):
        receipt = self.get_object()
        if request.method == "POST":
            return Response(
                returns.request_return(
                    request, receipt.pk, validated(SupplierReturnInput, request.data)
                ),
                status=201,
            )
        return self.respond_list(receipt.returns.all(), SupplierReturnSerializer)

    def list(self, request):
        qs = search(
            self.queryset,
            request,
            "reference",
            "order_line__order__number",
            "order_line__item__name",
        )
        if request.query_params.get("order"):
            qs = qs.filter(order_line__order_id=request.query_params["order"])
        if request.query_params.get("vendor"):
            qs = qs.filter(order_line__order__vendor_id=request.query_params["vendor"])
        return self.respond_list(qs)

    @extend_schema(responses=ReceivingReconciliationSerializer)
    @action(detail=False, methods=["get"])
    def reconciliation(self, request):
        from django.db import transaction

        from apps.accounting.services.setup import lock_company

        from ..services.reconciliation import receiving

        with transaction.atomic():
            lock_company()
            return Response(strings(receiving()))

    @extend_schema(request=ReceiptInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                services.receive(request, validated(ReceiptInput, request.data))
            ).data,
            status=201,
        )

    @extend_schema(request=CostCorrectionInput, responses=CostCorrectionResult)
    @action(detail=True, methods=["post"], url_path="cost-correction")
    def cost_correction(self, request, pk=None):
        return Response(
            costing.request_correction(
                request, self.get_object().pk, validated(CostCorrectionInput, request.data)
            ),
            status=201,
        )

    @extend_schema(responses=CostCorrectionSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="cost-corrections")
    def cost_corrections(self, request, pk=None):
        return self.respond_list(
            self.get_object().cost_corrections.order_by("-date", "-pk"), CostCorrectionSerializer
        )

    @extend_schema(request=MatchInput, responses=MatchSerializer(many=True))
    @action(detail=False, methods=["post"])
    def match(self, request):
        data = validated(MatchInput, request.data)
        return Response(
            MatchSerializer(
                services.match_bill(request, data["bill_line_id"], data["receipts"]), many=True
            ).data
        )
