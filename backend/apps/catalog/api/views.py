from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounting.money import strings
from apps.sales.api.base import DomainViewSet, search, sort, validated
from apps.sales.models import BillingItem

from .. import services
from ..models import Category, Unit
from . import serializers as s


class ReferenceViewSet(DomainViewSet):
    write_permissions = ("catalog.manage",)

    def list(self, request):
        return self.respond_list(search(self.queryset, request, "code", "name"))

    def create(self, request):
        data = validated(self.serializer_class, request.data)
        obj = services.save_reference(request, self.queryset.model, data)
        return Response(self.serializer_class(obj).data, status=201)

    def partial_update(self, request, pk=None):
        data = validated(self.serializer_class, request.data, partial=True)
        obj = services.save_reference(request, self.queryset.model, data, pk)
        return Response(self.serializer_class(obj).data)


@extend_schema(tags=["catalog"])
class CategoryViewSet(ReferenceViewSet):
    queryset = Category.objects.all()
    serializer_class = s.CategorySerializer


@extend_schema(tags=["catalog"])
class UnitViewSet(ReferenceViewSet):
    queryset = Unit.objects.all()
    serializer_class = s.UnitSerializer


@extend_schema(tags=["catalog"])
class ItemViewSet(DomainViewSet):
    queryset = BillingItem.objects.select_related("profile", "profile__unit")
    serializer_class = s.ItemSerializer
    write_permissions = ("catalog.manage",)

    def get_permissions(self):
        # Read-only calculations do not confer catalog-editing authority.
        if self.action in ("quote", "margin"):
            return [permission() for permission in self.permission_classes]
        return super().get_permissions()

    def list(self, request):
        qs = search(self.queryset, request, "code", "name", "description")
        if request.query_params.get("kind") == "product":
            from django.db.models import Q

            qs = qs.filter(Q(profile__kind__in=("stock", "nonstock")) | Q(profile__isnull=True))
        for key, field in (("kind", "profile__kind"), ("category", "profile__category_id")):
            if request.query_params.get(key) and request.query_params[key] != "product":
                qs = qs.filter(**{field: request.query_params[key]})
        if request.query_params.get("status") in ("active", "inactive"):
            qs = qs.filter(is_active=request.query_params["status"] == "active")
        return self.respond_list(sort(qs, request, ("code", "name"), "name"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=s.ItemInput)
    def create(self, request):
        obj = services.save_item(request, validated(s.ItemInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.ItemInput)
    def partial_update(self, request, pk=None):
        obj = services.save_item(request, validated(s.ItemInput, request.data), pk)
        return Response(self.serializer_class(obj).data)

    @extend_schema(request=s.PriceSerializer, responses=s.PriceSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def prices(self, request, pk=None):
        if request.method == "POST":
            price = services.add_price(request, pk, validated(s.PriceSerializer, request.data))
            return Response(s.PriceSerializer(price).data, status=201)
        page = self.paginate_queryset(self.get_object().prices.all())
        return self.get_paginated_response(s.PriceSerializer(page, many=True).data)

    @extend_schema(request=s.QuoteInput, responses=s.QuoteSerializer)
    @action(detail=True, methods=["post"])
    def quote(self, request, pk=None):
        data = validated(s.QuoteInput, request.data)
        data["on"] = data.pop("date")
        return Response(strings(services.quote(self.get_object(), **data)))

    @extend_schema(request=s.MarginInput, responses=s.MarginSerializer)
    @action(detail=True, methods=["post"])
    def margin(self, request, pk=None):
        data = validated(s.MarginInput, request.data)
        data["on"] = data.pop("date")
        return Response(strings(services.margin(self.get_object(), **data)))
