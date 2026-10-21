from django.urls import include, path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.accounting.api.serializers import DecimalText
from apps.accounting.money import strings
from apps.sales.api.base import DomainViewSet, search, validated

from . import services
from .models import (
    Asset,
    AssetAction,
    AssetDisposal,
    AssetEstimate,
    AssetEvidence,
    DepreciationCharge,
)


class AssetInput(serializers.Serializer):
    key = serializers.CharField(min_length=8, max_length=140)
    reason = serializers.CharField(max_length=1000)


class CapitalizationInput(AssetInput):
    tag = serializers.CharField(max_length=60)
    name = serializers.CharField(max_length=200)
    category = serializers.CharField(max_length=80)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    serial_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    custodian_reference = serializers.CharField(max_length=200, required=False, allow_blank=True)
    source_line_id = serializers.IntegerField(min_value=1)
    recognition_date = serializers.DateField()
    in_service_date = serializers.DateField()
    cost = DecimalText()
    residual = DecimalText()
    useful_life_months = serializers.IntegerField(min_value=1, max_value=1200)
    depreciation_account_id = serializers.IntegerField(min_value=1)


class DepreciationInput(AssetInput):
    month = serializers.DateField()
    recognition_date = serializers.DateField()


class CapitalizationReversalInput(AssetInput):
    recognition_date = serializers.DateField()


class EstimateInput(AssetInput):
    effective_date = serializers.DateField()
    remaining_months = serializers.IntegerField(min_value=1, max_value=1200)
    residual = DecimalText()


class DisposalInput(AssetInput):
    date = serializers.DateField()
    kind = serializers.ChoiceField(choices=["sale", "retirement", "write_off"])
    invoice_line_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    gain_account_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    loss_account_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class AssetMetadataInput(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    category = serializers.CharField(max_length=80, required=False)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    serial_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    custodian_reference = serializers.CharField(max_length=200, required=False, allow_blank=True)


class AssetSerializer(serializers.ModelSerializer):
    accumulated = serializers.SerializerMethodField()
    book_value = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    cancellation = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            "id",
            "tag",
            "name",
            "category",
            "description",
            "serial_number",
            "location",
            "custodian_reference",
            "source_line_id",
            "source_snapshot",
            "acquisition_date",
            "recognition_date",
            "in_service_date",
            "cost",
            "journal_id",
            "depreciation_account_id",
            "created_at",
            "accumulated",
            "book_value",
            "status",
            "cancellation",
        ]

    def get_accumulated(self, obj) -> str:
        return str(services.accumulated(obj))

    def get_book_value(self, obj) -> str:
        return (
            "0"
            if hasattr(obj, "disposal") or hasattr(obj, "cancellation")
            else str(obj.cost - services.accumulated(obj))
        )

    def get_status(self, obj) -> str:
        return (
            "cancelled"
            if hasattr(obj, "cancellation")
            else "disposed"
            if hasattr(obj, "disposal")
            else "active"
        )

    def get_cancellation(self, obj) -> dict | None:
        if not hasattr(obj, "cancellation"):
            return None
        return strings(
            {
                "date": obj.cancellation.date,
                "reason": obj.cancellation.reason,
                "journal_id": obj.cancellation.journal_id,
            }
        )


class AssetActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetAction
        fields = ["id", "operation", "key", "status", "result_id", "approval_id", "created_at"]


class DepreciationChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepreciationCharge
        fields = [
            "id",
            "asset_id",
            "estimate_id",
            "month",
            "recognition_date",
            "amount",
            "journal_id",
            "created_at",
        ]


class EstimateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetEstimate
        fields = [
            "id",
            "version",
            "effective_date",
            "remaining_months",
            "residual",
            "carrying_basis",
            "reason",
            "created_at",
        ]


class AssetDisposalSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetDisposal
        fields = [
            "id",
            "asset_id",
            "date",
            "kind",
            "invoice_line_id",
            "proceeds_base",
            "accumulated",
            "book_value",
            "gain_loss",
            "journal_id",
            "reason",
            "created_at",
        ]


class DepreciationScheduleRow(serializers.Serializer):
    month = serializers.DateField()
    scheduled = DecimalText()
    posted = DecimalText()
    recognition_date = serializers.DateField(allow_null=True)
    journal_id = serializers.UUIDField(allow_null=True)
    estimate_id = serializers.IntegerField()
    version = serializers.IntegerField()


class AssetEvidenceInput(serializers.Serializer):
    file = serializers.FileField()
    description = serializers.CharField(max_length=500)


class AssetEvidenceSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="file.original_name")

    class Meta:
        model = AssetEvidence
        fields = ["id", "file_id", "name", "description", "created_at"]


class AssetReconciliationSerializer(serializers.Serializer):
    cost = DecimalText()
    cost_ledger = DecimalText()
    cost_difference = DecimalText()
    depreciation = DecimalText()
    depreciation_ledger = DecimalText()
    depreciation_difference = DecimalText()


@extend_schema(tags=["assets"])
class AssetViewSet(DomainViewSet):
    queryset = Asset.objects.select_related("disposal", "cancellation").prefetch_related("charges")
    serializer_class = AssetSerializer
    write_permissions = ("assets.manage",)
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def list(self, request):
        qs = search(self.queryset, request, "tag", "name", "category", "serial_number", "location")
        status = request.query_params.get("status")
        if status == "active":
            qs = qs.filter(disposal__isnull=True, cancellation__isnull=True)
        elif status == "disposed":
            qs = qs.filter(disposal__isnull=False)
        elif status == "cancelled":
            qs = qs.filter(cancellation__isnull=False)
        return self.respond_list(qs.order_by("tag"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(responses=AssetReconciliationSerializer)
    @action(detail=False, methods=["get"])
    def reconciliation(self, request):
        return Response(strings(services.reconciliation()))

    @extend_schema(request=CapitalizationInput, responses=AssetActionSerializer)
    def create(self, request):
        obj = services.request_action(
            request, "capitalize", validated(CapitalizationInput, request.data)
        )
        return Response(AssetActionSerializer(obj).data, status=201)

    @extend_schema(request=AssetMetadataInput)
    def partial_update(self, request, pk=None):
        obj = services.update_metadata(
            request, self.get_object().pk, validated(AssetMetadataInput, request.data)
        )
        return Response(self.serializer_class(obj).data)

    @extend_schema(responses=DepreciationScheduleRow(many=True))
    @action(detail=True, methods=["get"])
    def schedule(self, request, pk=None):
        return Response(strings(services.schedule(self.get_object())))

    @extend_schema(request=DepreciationInput, responses=AssetActionSerializer)
    @action(detail=True, methods=["post"])
    def depreciate(self, request, pk=None):
        return self._request_action(request, "depreciation", DepreciationInput)

    @extend_schema(request=EstimateInput, responses=AssetActionSerializer)
    @action(detail=True, methods=["post"])
    def revise_estimate(self, request, pk=None):
        return self._request_action(request, "estimate", EstimateInput)

    @extend_schema(request=DisposalInput, responses=AssetActionSerializer)
    @action(detail=True, methods=["post"])
    def dispose(self, request, pk=None):
        return self._request_action(request, "disposal", DisposalInput)

    @extend_schema(request=CapitalizationReversalInput, responses=AssetActionSerializer)
    @action(detail=True, methods=["post"])
    def cancel_capitalization(self, request, pk=None):
        return self._request_action(request, "cancel", CapitalizationReversalInput)

    def _request_action(self, request, operation, input_class):
        obj = services.request_action(
            request,
            operation,
            {"asset_id": str(self.get_object().pk), **validated(input_class, request.data)},
        )
        return Response(AssetActionSerializer(obj).data, status=201)

    @extend_schema(responses=EstimateSerializer(many=True))
    @action(detail=True, methods=["get"])
    def estimates(self, request, pk=None):
        return self.respond_list(
            self.get_object().estimates.order_by("-version"), EstimateSerializer
        )

    @extend_schema(responses=AssetEvidenceSerializer(many=True))
    @action(detail=True, methods=["get"])
    def evidence(self, request, pk=None):
        return self.respond_list(
            self.get_object().evidence.select_related("file").order_by("-pk"),
            AssetEvidenceSerializer,
        )

    @extend_schema(request=AssetEvidenceInput, responses=AssetEvidenceSerializer)
    @evidence.mapping.post
    def add_evidence(self, request, pk=None):
        data = validated(AssetEvidenceInput, request.data)
        obj = services.add_evidence(
            request, self.get_object().pk, data["description"], data["file"]
        )
        return Response(AssetEvidenceSerializer(obj).data, status=201)


@extend_schema(tags=["assets"])
class DepreciationViewSet(DomainViewSet):
    queryset = DepreciationCharge.objects.all()
    serializer_class = DepreciationChargeSerializer

    def list(self, request):
        return self.respond_list(self.queryset.order_by("-recognition_date", "-pk"))


@extend_schema(tags=["assets"])
class DisposalViewSet(DomainViewSet):
    queryset = AssetDisposal.objects.all()
    serializer_class = AssetDisposalSerializer

    def list(self, request):
        return self.respond_list(self.queryset.order_by("-date", "-pk"))


class AcquisitionLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    journal_id = serializers.UUIDField()
    journal_number = serializers.CharField(source="journal.number")
    date = serializers.DateField(source="journal.journal_date")
    account_code = serializers.CharField(source="account.code")
    description = serializers.CharField()
    source_reference = serializers.CharField()
    currency = serializers.CharField()
    exchange_rate = DecimalText()
    base_debit = DecimalText()
    available_base = serializers.SerializerMethodField()

    def get_available_base(self, obj) -> str:
        return str(services.available_acquisition(obj))


@extend_schema(tags=["assets"])
class AcquisitionViewSet(DomainViewSet):
    serializer_class = AcquisitionLineSerializer
    queryset = services.JournalLine.objects.none()

    def list(self, request):
        qs = search(
            services.acquisition_lines(request.user),
            request,
            "journal__number",
            "description",
            "account__code",
            "source_reference",
        )
        return self.respond_list(qs.order_by("-journal__posting_date", "-pk"))


router = SimpleRouter()
router.register("register", AssetViewSet)
router.register("depreciation", DepreciationViewSet)
router.register("disposals", DisposalViewSet)
router.register("acquisitions", AcquisitionViewSet, basename="asset-acquisitions")
urlpatterns = [path("assets/", include(router.urls))]
