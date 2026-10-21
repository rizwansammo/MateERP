from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.money import strings
from apps.accounts.authorization import IsActiveUser, requires
from apps.catalog.models import ItemProfile
from apps.core.pagination import StandardPagination
from apps.sales.api.base import DomainViewSet, search, sort, validated

from .. import counts, services
from ..models import Location, Movement, StockCount
from . import serializers as s


@extend_schema(tags=["inventory"], responses=OpenApiTypes.OBJECT)
class OverviewView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request):
        return Response(services.overview())


@extend_schema(tags=["inventory"])
class LocationViewSet(DomainViewSet):
    queryset = Location.objects.all()
    serializer_class = s.LocationSerializer
    write_permissions = ("inventory.manage",)

    def list(self, request):
        return self.respond_list(search(self.queryset, request, "code", "name"))

    def create(self, request):
        obj = services.save_location(request, validated(self.serializer_class, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    def partial_update(self, request, pk=None):
        obj = services.save_location(
            request, validated(self.serializer_class, request.data, partial=True), pk
        )
        return Response(self.serializer_class(obj).data)


@extend_schema(tags=["inventory"])
class MovementViewSet(DomainViewSet):
    queryset = Movement.objects.select_related("item", "location")
    serializer_class = s.MovementSerializer

    def list(self, request):
        qs = search(self.queryset, request, "item__name", "item__code", "reason", "source_id")
        for key in ("item_id", "location_id", "kind"):
            if request.query_params.get(key):
                qs = qs.filter(**{key: request.query_params[key]})
        return self.respond_list(sort(qs, request, ("sequence", "date"), "-sequence"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)


@extend_schema(tags=["inventory"], responses=s.StockCountSerializer)
class AdjustmentView(APIView):
    permission_classes = [
        IsActiveUser,
        requires("finance.view", "inventory.manage", "inventory.post"),
    ]

    @extend_schema(request=s.AdjustmentInput)
    def post(self, request):
        return Response(
            s.StockCountSerializer(
                counts.submit(request, validated(s.AdjustmentInput, request.data))
            ).data,
            status=201,
        )


@extend_schema(tags=["inventory"])
class StockCountViewSet(DomainViewSet):
    queryset = StockCount.objects.all()
    serializer_class = s.StockCountSerializer

    def list(self, request):
        qs = self.queryset
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return self.respond_list(qs.order_by("-created_at", "-pk"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)


@extend_schema(tags=["inventory"], responses=s.MovementSerializer)
class TransferView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view", "inventory.manage")]

    @extend_schema(request=s.TransferInput)
    def post(self, request):
        return Response(
            s.MovementSerializer(
                services.transfer(request, validated(s.TransferInput, request.data))
            ).data,
            status=201,
        )


@extend_schema(tags=["inventory"], responses=s.ValuationSerializer)
class ValuationView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request):
        profiles = search(
            ItemProfile.objects.filter(kind="stock").select_related("item", "unit"),
            request,
            "item__code",
            "item__name",
        )
        pagination = StandardPagination()
        profiles = pagination.paginate_queryset(profiles.order_by("item__code"), request)
        rows = [
            {
                "id": p.item_id,
                "item_id": p.item_id,
                "code": p.item.code,
                "name": p.item.name,
                "unit": p.unit.code,
                "reorder_level": p.reorder_level,
                **services.position(p.item_id),
            }
            for p in profiles
        ]
        response = pagination.get_paginated_response(strings(rows))
        response.data["reconciliation"] = strings(services.reconciliation())
        return response


@extend_schema(tags=["inventory"], responses=s.PositionSerializer, parameters=[s.PositionInput])
class PositionView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request):
        data = validated(s.PositionInput, request.query_params)
        return Response(
            strings(services.position(data["item_id"], data.get("location_id"), data.get("date")))
        )
