import csv
import io

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import IsActiveUser, require, requires
from apps.audit.models import AuditEvent
from apps.company.services import get_business_settings, get_company
from apps.core.exceptions import BusinessRuleViolation
from apps.core.pagination import StandardPagination

from .. import reports
from ..models import (
    Account,
    AccountingPeriod,
    ExchangeRate,
    FiscalYear,
    JournalEntry,
    TaxCode,
    TaxRevision,
)
from ..money import strings
from ..services import posting, setup
from . import serializers as s


def validated(cls, data, **kwargs):
    obj = cls(data=data, **kwargs)
    obj.is_valid(raise_exception=True)
    return dict(obj.validated_data)


def dates(request):
    if request.query_params.get("period"):
        period_id = serializers.IntegerField(min_value=1).run_validation(
            request.query_params["period"]
        )
        period = get_object_or_404(AccountingPeriod, pk=period_id)
        return period.start, period.end
    end = serializers.DateField().run_validation(
        request.query_params.get("to", timezone.localdate().isoformat())
    )
    company = get_company()
    month = company.fiscal_year_start_month if company else 1
    year = end.year - (end.month < month)
    start = serializers.DateField().run_validation(
        request.query_params.get("from", f"{year}-{month:02d}-01")
    )
    if start > end:
        raise serializers.ValidationError({"from": "Start follows end."})
    return start, end


class FinanceView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]


@extend_schema(tags=["accounting"], responses=s.EnvelopeSerializer)
class ConfigView(FinanceView):
    def get(self, request):
        company = get_company()
        if not company:
            raise BusinessRuleViolation(
                "Set up the company profile first.", code="company_required"
            )
        obj = get_business_settings()
        return Response(
            {
                "base_currency": company.base_currency,
                "fiscal_year_start_month": company.fiscal_year_start_month,
                "enabled_currencies": obj.enabled_currencies,
                "currency_display": obj.currency_display,
                "number_grouping": obj.number_grouping,
            }
        )


@extend_schema(tags=["tax accounting"], responses=s.EnvelopeSerializer)
class TaxPositionView(FinanceView):
    def get(self, request):
        from decimal import Decimal

        from django.db.models import Sum

        from ..models import JournalLine

        inputs = TaxRevision.objects.values_list("input_account_id", flat=True).distinct()
        outputs = TaxRevision.objects.values_list("output_account_id", flat=True).distinct()
        qs = JournalLine.objects.filter(journal__status="posted")
        totals = qs.aggregate(
            idr=Sum("base_debit", filter=Q(account_id__in=inputs)),
            icr=Sum("base_credit", filter=Q(account_id__in=inputs)),
            odr=Sum("base_debit", filter=Q(account_id__in=outputs)),
            ocr=Sum("base_credit", filter=Q(account_id__in=outputs)),
        )
        incoming = (totals["idr"] or Decimal(0)) - (totals["icr"] or Decimal(0))
        outgoing = (totals["ocr"] or Decimal(0)) - (totals["odr"] or Decimal(0))
        return Response(
            strings({"input": incoming, "output": outgoing, "net": outgoing - incoming})
        )


class FinanceViewSet(viewsets.GenericViewSet):
    permission_classes = [IsActiveUser, requires("finance.view")]
    pagination_class = StandardPagination

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method not in ("GET", "HEAD", "OPTIONS"):
            permissions.append(requires("accounting.manage")())
        return permissions

    def respond_list(self, qs, cls=None):
        page = self.paginate_queryset(qs)
        return self.get_paginated_response((cls or self.serializer_class)(page, many=True).data)


@extend_schema(tags=["accounting"])
class AccountViewSet(FinanceViewSet):
    serializer_class = s.AccountSerializer
    queryset = Account.objects.all()

    def list(self, request):
        qs = self.queryset.all()
        if request.query_params.get("search"):
            q = request.query_params["search"]
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        if request.query_params.get("type"):
            qs = qs.filter(account_type=request.query_params["type"])
        if request.query_params.get("active") == "true":
            qs = qs.filter(is_active=True, is_postable=True)
        order = request.query_params.get("sort", "code")
        return self.respond_list(
            qs.order_by(order if order.lstrip("-") in ("code", "name", "account_type") else "code")
        )

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    def create(self, request):
        obj = setup.save_account(request, validated(self.serializer_class, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    def partial_update(self, request, pk=None):
        obj = setup.save_account(
            request, validated(self.serializer_class, request.data, partial=True), pk
        )
        return Response(self.serializer_class(obj).data)

    @extend_schema(responses=s.EnvelopeSerializer)
    @action(detail=False, methods=["get", "post"], url_path="setup")
    def chart_setup(self, request):
        if request.method == "GET":
            return Response(
                {
                    "accounts": [
                        {"code": r[0], "name": r[1], "type": r[2], "postable": r[4]}
                        for r in setup.STARTER
                    ]
                }
            )
        return Response(self.serializer_class(setup.setup_chart(request), many=True).data)

    @action(detail=False, methods=["get"])
    def tree(self, request):
        return Response(self.serializer_class(self.queryset.all(), many=True).data)


@extend_schema(tags=["journals"])
class JournalViewSet(FinanceViewSet):
    serializer_class = s.JournalSerializer
    queryset = JournalEntry.objects.select_related("created_by", "reversed_by").prefetch_related(
        "lines__account"
    )

    def list(self, request):
        qs = self.queryset.all()
        if "opening-balances" in request.path:
            qs = qs.filter(kind="opening")
        for field in ("status", "kind"):
            if request.query_params.get(field):
                qs = qs.filter(**{field: request.query_params[field]})
        if request.query_params.get("search"):
            q = request.query_params["search"]
            qs = qs.filter(Q(description__icontains=q) | Q(number__icontains=q))
        if request.query_params.get("from") or request.query_params.get("to"):
            start, end = dates(request)
            qs = qs.filter(posting_date__range=(start, end))
        order = request.query_params.get("sort", "-posting_date")
        return self.respond_list(
            qs.order_by(
                order
                if order.lstrip("-") in ("posting_date", "number", "status", "created_at")
                else "-posting_date",
                "id",
            )
        )

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=s.JournalInput)
    def create(self, request):
        data = validated(s.JournalInput, request.data)
        if "opening-balances" in request.path:
            data["kind"] = "opening"
        obj = posting.save_draft(request, data)
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.JournalInput)
    def partial_update(self, request, pk=None):
        obj = posting.save_draft(request, validated(s.JournalInput, request.data), pk)
        return Response(self.serializer_class(obj).data)

    @extend_schema(request=None, responses=s.EnvelopeSerializer)
    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        return Response(posting.validation(self.get_object()))

    @extend_schema(request=s.DecisionInput, responses=s.EnvelopeSerializer)
    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        data = validated(s.DecisionInput, request.data)
        journal, replay = posting.post_draft(
            request, pk, request.headers.get("Idempotency-Key") or data.get("posting_key")
        )
        return Response(
            {
                "status": "pending_approval" if journal.status == "pending" else journal.status,
                "replayed": replay,
                "journal": self.serializer_class(journal).data,
            }
        )

    @extend_schema(request=s.DecisionInput)
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        data = validated(s.DecisionInput, request.data)
        if "posting_date" not in data:
            raise serializers.ValidationError(
                {"posting_date": "Choose an open-period reversal date."}
            )
        obj = posting.reverse(
            request,
            pk,
            data["posting_date"],
            data["reason"],
            request.headers.get("Idempotency-Key") or data.get("posting_key"),
        )
        return Response(self.serializer_class(obj).data)

    @extend_schema(responses=s.EnvelopeSerializer)
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        self.get_object()
        rows = AuditEvent.objects.filter(target_id=pk).values(
            "action", "occurred_at", "actor_label", "reason"
        )
        return Response({"events": list(rows[:100])})


@extend_schema(tags=["periods"])
class YearViewSet(FinanceViewSet):
    serializer_class = s.YearSerializer
    queryset = FiscalYear.objects.all()

    def list(self, request):
        return self.respond_list(self.queryset)

    @extend_schema(request=s.DateInput)
    def create(self, request):
        obj = setup.create_year(request, validated(s.DateInput, request.data)["start"])
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.DecisionInput)
    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        return Response(
            self.serializer_class(setup.set_period(request, pk, True, fiscal=True)).data
        )

    @extend_schema(request=s.DecisionInput)
    @action(detail=True, methods=["post"], url_path="reopen")
    def reopen(self, request, pk=None):
        data = validated(s.DecisionInput, request.data)
        return Response(
            self.serializer_class(
                setup.set_period(request, pk, False, data["reason"], fiscal=True)
            ).data
        )


@extend_schema(tags=["periods"])
class PeriodViewSet(FinanceViewSet):
    serializer_class = s.PeriodSerializer
    queryset = AccountingPeriod.objects.all()

    def list(self, request):
        qs = self.queryset.all()
        if request.query_params.get("year"):
            qs = qs.filter(
                fiscal_year_id=serializers.IntegerField(min_value=1).run_validation(
                    request.query_params["year"]
                )
            )
        return self.respond_list(qs)

    @extend_schema(request=s.DecisionInput)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return Response(self.serializer_class(setup.set_period(request, pk, True)).data)

    @extend_schema(request=s.DecisionInput)
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return Response(
            self.serializer_class(
                setup.set_period(
                    request, pk, False, validated(s.DecisionInput, request.data)["reason"]
                )
            ).data
        )


@extend_schema(tags=["exchange rates"])
class RateViewSet(FinanceViewSet):
    serializer_class = s.RateSerializer
    queryset = ExchangeRate.objects.all()

    @extend_schema(request=s.ConversionInput, responses=s.EnvelopeSerializer)
    @action(detail=False, methods=["post"])
    def preview(self, request):
        from ..money import convert, money

        data = validated(s.ConversionInput, request.data)
        company = get_company()
        if not company:
            raise BusinessRuleViolation("Set up the company profile first.")
        value = money(data["amount"], data["currency"])
        rate, source = setup.rate_for(data["currency"], data["on"], company.base_currency)
        return Response(
            strings(
                {
                    "amount": value,
                    "currency": data["currency"],
                    "exchange_rate": rate,
                    "source": source,
                    "base_currency": company.base_currency,
                    "base_amount": convert(value, rate, company.base_currency),
                }
            )
        )

    def list(self, request):
        qs = self.queryset.all()
        if request.query_params.get("currency"):
            qs = qs.filter(currency=request.query_params["currency"])
        return self.respond_list(qs)

    @extend_schema(request=s.RateInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                setup.add_rate(request, validated(s.RateInput, request.data))
            ).data,
            status=201,
        )


@extend_schema(tags=["tax accounting"])
class TaxViewSet(FinanceViewSet):
    serializer_class = s.TaxSerializer
    queryset = TaxCode.objects.prefetch_related("revisions")

    def list(self, request):
        return self.respond_list(self.queryset)

    @extend_schema(request=s.TaxInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                setup.save_tax(request, validated(s.TaxInput, request.data))
            ).data,
            status=201,
        )

    @extend_schema(request=s.TaxInput)
    def partial_update(self, request, pk=None):
        return Response(
            self.serializer_class(
                setup.save_tax(request, validated(s.TaxInput, request.data, partial=True), pk)
            ).data
        )


def export_csv(data, name):
    rows = data.get("results", data.get("rows", []))
    buf = io.StringIO()
    writer = csv.writer(buf)
    keys = list(rows[0]) if rows else ["No posted activity"]
    writer.writerow(keys)
    for row in rows:
        writer.writerow(
            [
                ("'" + str(row[k]))
                if str(row[k]).startswith(("=", "+", "-", "@", "\t", "\r"))
                else str(row[k])
                for k in keys
            ]
        )
    for key, value in data.items():
        if key not in ("rows", "results") and not isinstance(value, dict | list):
            writer.writerow([key, str(value)])
    response = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    response["Cache-Control"] = "private, no-store"
    return response


@extend_schema(tags=["financial reports"], responses=s.EnvelopeSerializer)
class ReportView(FinanceView):
    def get(self, request, which="ledger"):
        if which not in ("tb", "pnl", "bs", "cf", "ledger"):
            raise serializers.ValidationError({"report": "Unknown report."})
        start, end = dates(request)
        data = reports.report(which, start, end)
        if request.query_params.get("export") == "csv":
            require(request.user, "reports.export")
            return export_csv(data, which)
        return Response(data)


@extend_schema(tags=["financial reports"], responses=s.EnvelopeSerializer)
class LedgerView(FinanceView):
    @extend_schema(operation_id="account_ledger_entries")
    def get(self, request, pk):
        get_object_or_404(Account, pk=pk)
        start, end = dates(request)
        page = serializers.IntegerField(min_value=1).run_validation(
            request.query_params.get("page", 1)
        )
        size = serializers.IntegerField(min_value=1, max_value=100).run_validation(
            request.query_params.get("page_size", 25)
        )
        data = reports.ledger(
            pk, start, end, page=page, page_size=size, search=request.query_params.get("search", "")
        )
        if request.query_params.get("export") == "csv":
            require(request.user, "reports.export")
            data = reports.ledger(
                pk,
                start,
                end,
                page=1,
                page_size=10**9,
                search=request.query_params.get("search", ""),
            )
            return export_csv(data, "ledger")
        return Response(data)
