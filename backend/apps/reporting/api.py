from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.urls import path
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.api.serializers import DecimalText
from apps.accounts.authorization import IsActiveUser, require, requires
from apps.company.services import get_company
from apps.core.pagination import StandardPagination
from apps.sales.api.base import search, validated

from . import cash_flow, catalog, dashboard
from .models import CashFlowReview


def report_dates(request):
    company = get_company()
    current = (
        timezone.localdate(timezone=ZoneInfo(company.time_zone))
        if company
        else timezone.localdate()
    )
    preset = request.query_params.get(
        "range", "custom" if request.query_params.get("from") else "year"
    )
    if preset == "month":
        start, end = current.replace(day=1), current
    elif preset == "previous":
        end = current.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif preset == "quarter":
        start, end = date(current.year, ((current.month - 1) // 3) * 3 + 1, 1), current
    elif preset == "year":
        month = company.fiscal_year_start_month if company else 1
        start, end = date(current.year - (current.month < month), month, 1), current
    elif preset == "custom":
        field = serializers.DateField()
        start = field.run_validation(request.query_params.get("from"))
        end = field.run_validation(request.query_params.get("to"))
    else:
        raise serializers.ValidationError(
            {"range": "Choose month, previous, quarter, year or custom."}
        )
    if start > end or (end - start).days > 3660:
        raise serializers.ValidationError(
            {"from": "Choose an ordered date range of at most ten years."}
        )
    return start, end


@extend_schema(tags=["reporting"], responses=OpenApiTypes.OBJECT)
class DashboardView(APIView):
    permission_classes = [IsActiveUser]

    def get(self, request):
        start, end = report_dates(request)
        return Response(dashboard.summary(request.user, start, end))


class CatalogRow(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    group = serializers.CharField()
    description = serializers.CharField()
    route = serializers.CharField()
    permissions = serializers.ListField(child=serializers.CharField())


@extend_schema(tags=["reporting"], responses=CatalogRow(many=True))
class CatalogView(APIView):
    permission_classes = [IsActiveUser]

    def get(self, request):
        return Response(catalog.visible(request.user))


class GlobalSearchResultSerializer(serializers.Serializer):
    category = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    href = serializers.CharField()


@extend_schema(tags=["reporting"], responses=GlobalSearchResultSerializer(many=True))
class GlobalSearchView(APIView):
    permission_classes = [IsActiveUser]

    def get(self, request):
        from .search import global_results

        term = request.query_params.get("q", "")
        if not isinstance(term, str) or len(term) > 100:
            raise serializers.ValidationError({"q": "Search query must be at most 100 characters."})
        return Response(global_results(request.user, term))


class CashAllocation(serializers.Serializer):
    category = serializers.ChoiceField(choices=cash_flow.CATEGORIES)
    amount = DecimalText()


class CashReviewInput(serializers.Serializer):
    journal_id = serializers.UUIDField()
    expected_version = serializers.IntegerField(min_value=0, required=False)
    allocations = CashAllocation(many=True, allow_empty=False, max_length=20)
    reason = serializers.CharField(max_length=1000)


class CashReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashFlowReview
        fields = [
            "id",
            "journal_id",
            "version",
            "allocations",
            "reason",
            "created_by_id",
            "created_at",
        ]


class CashMovementSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.CharField()
    posting_date = serializers.DateField()
    description = serializers.CharField()
    source_type = serializers.CharField()
    cash_debit = DecimalText()
    cash_credit = DecimalText()


@extend_schema(tags=["reporting"], responses=CashMovementSerializer(many=True))
class CashMovementView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request):
        start, end = report_dates(request)
        rows = cash_flow.cash_movements(start, end).exclude(kind="transfer")
        rows = search(rows, request, "number", "description")
        pagination = StandardPagination()
        page = pagination.paginate_queryset(rows, request)
        return pagination.get_paginated_response(CashMovementSerializer(page, many=True).data)


@extend_schema(tags=["reporting"])
class CashReviewView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    @extend_schema(responses=CashReviewSerializer(many=True))
    def get(self, request):
        query = validated(CashReviewFilter, request.query_params)
        rows = CashFlowReview.objects.filter(journal_id=query["journal_id"]).order_by("-version")
        pagination = StandardPagination()
        page = pagination.paginate_queryset(rows, request)
        return pagination.get_paginated_response(CashReviewSerializer(page, many=True).data)

    @extend_schema(request=CashReviewInput, responses=CashReviewSerializer)
    def post(self, request):
        require(request.user, "reports.classify", "finance.view")
        obj = cash_flow.classify(request, validated(CashReviewInput, request.data))
        return Response(CashReviewSerializer(obj).data, status=201)


class CashReviewFilter(serializers.Serializer):
    journal_id = serializers.UUIDField()


class ReportFilter(serializers.Serializer):
    currency = serializers.CharField(max_length=3, required=False)
    customer_id = serializers.IntegerField(min_value=1, required=False)
    vendor_id = serializers.IntegerField(min_value=1, required=False)
    item_id = serializers.IntegerField(min_value=1, required=False)
    location_id = serializers.IntegerField(min_value=1, required=False)
    account_id = serializers.IntegerField(min_value=1, required=False)
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    sort = serializers.CharField(max_length=50, required=False)


@extend_schema(tags=["reporting"], responses=OpenApiTypes.OBJECT)
class DataView(APIView):
    permission_classes = [IsActiveUser]

    def get(self, request, which):
        from django.db import transaction

        from apps.accounting.api.views import export_csv
        from apps.accounting.services.setup import lock_company

        from .data import report_rows

        report = catalog.BY_KEY.get(which)
        if report is None:
            from rest_framework.exceptions import NotFound

            raise NotFound()
        require(request.user, *report.permissions)
        start, end = report_dates(request)
        with transaction.atomic():
            company = lock_company()
            result = report_rows(
                request.user,
                which,
                start,
                end,
                company,
                validated(ReportFilter, request.query_params),
            )
            if request.query_params.get("export") == "csv":
                require(request.user, "reports.export")
                return export_csv(result, which)
            pagination = StandardPagination()
            page = pagination.paginate_queryset(result.pop("rows"), request)
            response = pagination.get_paginated_response(page)
            response.data.update(result)
            return response


urlpatterns = [
    path("reporting/dashboard/", DashboardView.as_view()),
    path("reporting/catalog/", CatalogView.as_view()),
    path("reporting/search/", GlobalSearchView.as_view()),
    path("reporting/cash-movements/", CashMovementView.as_view()),
    path("reporting/cash-reviews/", CashReviewView.as_view()),
    path("reporting/reports/<str:which>/", DataView.as_view()),
]
