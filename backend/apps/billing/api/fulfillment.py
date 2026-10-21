"""Source-owned fulfillment; dispatch, recognition and invoicing are separate actions."""

from django.db.models import Sum
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounting.api.serializers import DecimalText
from apps.sales.api.base import DomainViewSet, search, validated

from ..fulfillment_models import (
    ControlTransfer,
    CustomerReturn,
    Dispatch,
    DispatchRecall,
    FulfillmentPolicy,
)
from ..services import recognition


class FulfillmentPolicyInput(serializers.Serializer):
    order_line_id = serializers.IntegerField(min_value=1)
    trigger = serializers.ChoiceField(choices=["control_transfer", "invoice"])
    contract_reference = serializers.CharField(max_length=200)
    reason = serializers.CharField(max_length=1000)


class FulfillmentPolicySerializer(serializers.ModelSerializer):
    order_line_id = serializers.IntegerField(read_only=True)
    controlled_quantity = serializers.SerializerMethodField()

    class Meta:
        model = FulfillmentPolicy
        fields = [
            "id",
            "order_line_id",
            "trigger",
            "contract_reference",
            "reason",
            "net_contract",
            "revenue_account_id",
            "snapshot",
            "controlled_quantity",
            "created_at",
        ]

    def get_controlled_quantity(self, obj) -> str:
        return str(obj.transfers.aggregate(q=Sum("quantity"))["q"] or 0)


class FulfillmentEventInput(serializers.Serializer):
    policy_id = serializers.IntegerField(min_value=1)
    date = serializers.DateField()
    quantity = DecimalText()
    reference = serializers.CharField(max_length=100)
    evidence = serializers.CharField(max_length=1000)
    key = serializers.CharField(min_length=8, max_length=140)


class DispatchInput(FulfillmentEventInput):
    from_location_id = serializers.IntegerField(min_value=1)
    transit_location_id = serializers.IntegerField(min_value=1)


class ControlTransferInput(FulfillmentEventInput):
    location_id = serializers.IntegerField(min_value=1)
    dispatch_id = serializers.UUIDField(required=False)


class FulfillmentReturnInput(serializers.Serializer):
    transfer_id = serializers.UUIDField()
    date = serializers.DateField()
    quantity = DecimalText()
    location_id = serializers.IntegerField(min_value=1)
    reference = serializers.CharField(max_length=100)
    reason = serializers.CharField(max_length=1000)
    key = serializers.CharField(min_length=8, max_length=140)


class DispatchRecallInput(serializers.Serializer):
    date = serializers.DateField()
    quantity = DecimalText()
    location_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=1000)
    key = serializers.CharField(min_length=8, max_length=130)


class DispatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dispatch
        fields = [
            "id",
            "policy_id",
            "date",
            "quantity",
            "from_location_id",
            "transit_location_id",
            "reference",
            "evidence",
            "movement_id",
            "created_at",
        ]


class ControlTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = ControlTransfer
        fields = [
            "id",
            "policy_id",
            "dispatch_id",
            "location_id",
            "date",
            "quantity",
            "reference",
            "evidence",
            "currency",
            "net_native",
            "base_revenue",
            "base_cogs",
            "journal_id",
            "movement_id",
            "created_at",
        ]


class CustomerReturnSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerReturn
        fields = [
            "id",
            "transfer_id",
            "date",
            "quantity",
            "base_cost",
            "location_id",
            "movement_id",
            "reference",
            "reason",
            "created_at",
        ]


class DispatchRecallSerializer(serializers.ModelSerializer):
    class Meta:
        model = DispatchRecall
        fields = [
            "id",
            "dispatch_id",
            "date",
            "quantity",
            "location_id",
            "movement_id",
            "reason",
            "created_at",
        ]


class FulfillmentReadSet(DomainViewSet):
    def list(self, request):
        qs = (
            search(self.queryset, request, "reference")
            if hasattr(self.queryset.model, "reference")
            else self.queryset
        )
        order = request.query_params.get("order_id")
        if order:
            prefix = "order_line" if self.queryset.model is FulfillmentPolicy else self.order_prefix
            qs = qs.filter(**{f"{prefix}__order_id": order})
        if request.query_params.get("policy_id") and self.queryset.model in (
            Dispatch,
            ControlTransfer,
        ):
            qs = qs.filter(policy_id=request.query_params["policy_id"])
        return self.respond_list(qs.order_by("-created_at", "-pk"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)


@extend_schema(tags=["fulfillment"])
class FulfillmentPolicyViewSet(FulfillmentReadSet):
    queryset = FulfillmentPolicy.objects.all()
    serializer_class = FulfillmentPolicySerializer
    write_permissions = ("fulfillment.manage",)

    @extend_schema(request=FulfillmentPolicyInput)
    def create(self, request):
        obj = recognition.configure(request, validated(FulfillmentPolicyInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)


@extend_schema(tags=["fulfillment"])
class DispatchViewSet(FulfillmentReadSet):
    queryset = Dispatch.objects.all()
    order_prefix = "policy__order_line"
    serializer_class = DispatchSerializer
    write_permissions = ("fulfillment.manage",)

    @extend_schema(request=DispatchInput)
    def create(self, request):
        obj = recognition.dispatch(request, validated(DispatchInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=DispatchRecallInput, responses=DispatchRecallSerializer)
    @action(detail=True, methods=["post"])
    def recall(self, request, pk=None):
        obj = recognition.recall_dispatch(
            request, self.get_object().pk, validated(DispatchRecallInput, request.data)
        )
        return Response(DispatchRecallSerializer(obj).data, status=201)


@extend_schema(tags=["fulfillment"])
class ControlTransferViewSet(FulfillmentReadSet):
    queryset = ControlTransfer.objects.all()
    order_prefix = "policy__order_line"
    serializer_class = ControlTransferSerializer
    write_permissions = ("fulfillment.manage",)

    @extend_schema(request=ControlTransferInput)
    def create(self, request):
        obj = recognition.transfer_control(request, validated(ControlTransferInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)


@extend_schema(tags=["fulfillment"])
class CustomerReturnViewSet(FulfillmentReadSet):
    queryset = CustomerReturn.objects.all()
    order_prefix = "transfer__policy__order_line"
    serializer_class = CustomerReturnSerializer
    write_permissions = ("fulfillment.manage",)

    @extend_schema(request=FulfillmentReturnInput)
    def create(self, request):
        obj = recognition.accept_return(request, validated(FulfillmentReturnInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)


@extend_schema(tags=["fulfillment"])
class DispatchRecallViewSet(FulfillmentReadSet):
    queryset = DispatchRecall.objects.all()
    order_prefix = "dispatch__policy__order_line"
    serializer_class = DispatchRecallSerializer
