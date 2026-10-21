from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.authorization import IsActiveUser, requires
from apps.sales.api.base import DomainViewSet, search, validated

from ..models import HistoricalRecord, HistoricalTreatment
from ..services import onboarding
from .serializers import DecimalText


class TreatmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoricalTreatment
        fields = [
            "id",
            "mode",
            "recognition_date",
            "reason",
            "status",
            "approval_id",
            "journal_id",
            "expense_id",
            "founder_transaction_id",
            "vendor_bill_id",
            "personal_settlement_id",
            "approved_by_id",
        ]


class RecordSerializer(serializers.ModelSerializer):
    treatment = serializers.SerializerMethodField()

    def get_treatment(self, obj) -> dict | None:
        treatment = obj.treatments.order_by("-pk").first()
        return TreatmentSerializer(treatment).data if treatment else None

    class Meta:
        model = HistoricalRecord
        fields = [
            "id",
            "external_reference",
            "original_date",
            "description",
            "currency",
            "amount",
            "payment_source",
            "funding_classification",
            "pre_registration",
            "party_id",
            "evidence_id",
            "notes",
            "created_by_id",
            "created_at",
            "treatment",
        ]
        read_only_fields = ["id", "evidence_id", "created_by_id", "created_at", "treatment"]


class RecordInput(serializers.ModelSerializer):
    amount = DecimalText()
    party_id = serializers.IntegerField(required=False, allow_null=True)
    file = serializers.FileField(required=False)

    class Meta:
        model = HistoricalRecord
        fields = [
            "external_reference",
            "original_date",
            "description",
            "currency",
            "amount",
            "payment_source",
            "funding_classification",
            "pre_registration",
            "party_id",
            "notes",
            "file",
        ]
        extra_kwargs = {"external_reference": {"validators": []}}


class TreatmentInput(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["reconstructed", "opening_only", "linked"])
    recognition_date = serializers.DateField()
    reason = serializers.CharField(max_length=2000)
    payload = serializers.DictField(required=False)


@extend_schema(tags=["historical-onboarding"])
class HistoricalViewSet(DomainViewSet):
    queryset = HistoricalRecord.objects.prefetch_related("treatments")
    serializer_class = RecordSerializer
    permission_classes = [IsActiveUser, requires("onboarding.manage", "finance.view")]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = super().get_queryset()
        return onboarding.visible_records(self.request.user, qs)

    def list(self, request):
        qs = search(
            self.get_queryset(), request, "external_reference", "description", "payment_source"
        )
        if request.query_params.get("mode"):
            qs = qs.filter(
                treatments__mode=request.query_params["mode"],
                treatments__status__in=("pending", "approved"),
            ).distinct()
        return self.respond_list(qs)

    @extend_schema(request=RecordInput)
    def create(self, request):
        data = validated(RecordInput, request.data)
        obj = onboarding.document(request, data, data.pop("file", None))
        return Response(self.serializer_class(obj).data, status=201)

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=TreatmentInput, responses=TreatmentSerializer)
    @action(detail=True, methods=["post"])
    def treatment(self, request, pk=None):
        obj = onboarding.request_treatment(
            request, self.get_object().pk, validated(TreatmentInput, request.data)
        )
        return Response(TreatmentSerializer(obj).data, status=201)
