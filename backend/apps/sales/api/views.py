from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.money import strings
from apps.accounts.authorization import IsActiveUser, requires

from .. import calculation, services
from ..models import BillingItem, Customer, Project, SalesOrder
from . import serializers as s
from .base import DomainViewSet, search, sort, validated


@extend_schema(tags=["sales"])
class CustomerViewSet(DomainViewSet):
    serializer_class = s.CustomerSerializer
    queryset = Customer.objects.all()
    write_permissions = ("sales.manage",)

    def list(self, request):
        qs = search(self.queryset, request, "name", "code", "email", "contact_name", "city")
        status = request.query_params.get("status")
        if status in ("active", "inactive"):
            qs = qs.filter(is_active=status == "active")
        page = self.paginate_queryset(sort(qs, request, ("name", "code", "created_at"), "name"))
        data = self.serializer_class(page, many=True).data
        from apps.billing.services.reconciliation import customer_balances

        balances = customer_balances([c.pk for c in page])
        for row in data:
            row["balances"] = strings(balances.get(row["id"], {}))
        return self.get_paginated_response(data)

    def retrieve(self, request, pk=None):
        return Response(s.CustomerDetailSerializer(self.get_object()).data)

    def create(self, request):
        obj = services.save_customer(request, validated(self.serializer_class, request.data))
        return Response(s.CustomerDetailSerializer(obj).data, status=201)

    def partial_update(self, request, pk=None):
        data = validated(self.serializer_class, request.data, partial=True)
        data.pop("code", None)
        obj = services.save_customer(request, data, pk)
        return Response(s.CustomerDetailSerializer(obj).data)

    @extend_schema(request=s.ContactSerializer, responses=s.ContactSerializer)
    @action(detail=True, methods=["post"], url_path="contacts")
    def add_contact(self, request, pk=None):
        obj = services.save_contact(request, pk, validated(s.ContactSerializer, request.data))
        return Response(s.ContactSerializer(obj).data, status=201)

    @extend_schema(request=s.ContactSerializer, responses=s.ContactSerializer)
    @action(detail=True, methods=["patch"], url_path=r"contacts/(?P<contact_id>\d+)")
    def update_contact(self, request, pk=None, contact_id=None):
        data = validated(s.ContactSerializer, request.data, partial=True)
        obj = services.save_contact(request, pk, data, contact_id)
        return Response(s.ContactSerializer(obj).data)


@extend_schema(tags=["sales"])
class ProjectViewSet(DomainViewSet):
    serializer_class = s.ProjectSerializer
    queryset = Project.objects.select_related("customer").prefetch_related("milestones")
    write_permissions = ("sales.manage",)

    def list(self, request):
        qs = search(self.queryset, request, "reference", "name", "customer__name")
        if request.query_params.get("customer"):
            qs = qs.filter(customer_id=request.query_params["customer"])
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return self.respond_list(sort(qs, request, ("reference", "name"), "reference"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=s.ProjectInput)
    def create(self, request):
        obj = services.save_project(request, validated(s.ProjectInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.ProjectInput)
    def partial_update(self, request, pk=None):
        data = validated(s.ProjectInput, request.data, partial=True)
        obj = services.save_project(request, data, pk)
        return Response(self.serializer_class(obj).data)


@extend_schema(tags=["sales"])
class ItemViewSet(DomainViewSet):
    serializer_class = s.ItemSerializer
    queryset = BillingItem.objects.all()
    write_permissions = ("sales.manage",)

    def list(self, request):
        qs = search(self.queryset, request, "code", "name")
        if request.query_params.get("status") == "active":
            qs = qs.filter(is_active=True)
        return self.respond_list(sort(qs, request, ("name", "code"), "name"))

    def create(self, request):
        obj = services.save_item(request, validated(self.serializer_class, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    def partial_update(self, request, pk=None):
        data = validated(self.serializer_class, request.data, partial=True)
        return Response(self.serializer_class(services.save_item(request, data, pk)).data)


@extend_schema(tags=["sales"])
class OrderViewSet(DomainViewSet):
    serializer_class = s.OrderSerializer
    queryset = SalesOrder.objects.select_related("customer").prefetch_related("lines")
    write_permissions = ("sales.manage",)

    def list(self, request):
        qs = search(
            self.queryset, request, "number", "title", "customer__name", "customer_reference"
        )
        for param, field in (("status", "status"), ("customer", "customer_id")):
            if request.query_params.get(param):
                qs = qs.filter(**{field: request.query_params[param]})
        return self.respond_list(sort(qs, request, ("order_date", "number"), "-order_date"))

    def retrieve(self, request, pk=None):
        order = self.get_object()
        data = self.serializer_class(order).data
        done = services.order_invoiced_quantities(order)
        for line in data["lines"]:
            line["invoiced_quantity"] = strings(done.get(line["id"], 0))
        return Response(data)

    @extend_schema(request=s.OrderInput)
    def create(self, request):
        obj = services.save_order(request, validated(s.OrderInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.OrderInput)
    def partial_update(self, request, pk=None):
        data = validated(s.OrderInput, request.data, partial=True)
        return Response(self.serializer_class(services.save_order(request, data, pk)).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return Response(self.serializer_class(services.confirm_order(request, pk)).data)

    @extend_schema(request=s.ReasonInput)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reason = validated(s.ReasonInput, request.data)["reason"]
        return Response(self.serializer_class(services.cancel_order(request, pk, reason)).data)


def calculation_payload(result):
    """API shape of a calculation result: decimal strings only."""
    return strings(result)


@extend_schema(tags=["sales"], request=s.CalculateInput, responses=s.ReasonInput)
class CalculateView(APIView):
    """Server-authoritative totals for an unsaved document (no side effects)."""

    permission_classes = [IsActiveUser, requires("finance.view")]

    def post(self, request):
        data = validated(s.CalculateInput, request.data)
        result = calculation.calculate(
            currency=data["currency"],
            on=data["date"],
            lines=data["lines"],
            prices_include_tax=data["prices_include_tax"],
            discount_type=data["discount_type"],
            discount_value=data["discount_value"],
        )
        return Response(calculation_payload(result))
