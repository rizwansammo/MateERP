from datetime import date

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounting import reports
from apps.accounting.api.serializers import DecisionInput, EnvelopeSerializer, JournalSerializer
from apps.accounting.api.views import FinanceView, FinanceViewSet, dates, validated
from apps.accounting.models import AccountingPeriod, JournalLine
from apps.accounting.money import strings

from .. import services
from ..models import BankAccount, Reconciliation
from . import serializers as s


def reconciliation_data(obj):
    stmt = obj.statement
    lines = []
    for line in stmt.lines.all():
        group = line.matches.filter(is_active=True).first()
        lines.append(
            {
                "id": line.pk,
                "date": line.date,
                "description": line.description,
                "reference": line.reference,
                "amount": line.amount,
                "match_group_id": group.group_id if group else None,
            }
        )
    return strings(
        {
            "id": obj.pk,
            "bank_account_id": stmt.bank_account_id,
            "bank_account_name": stmt.bank_account.name,
            "currency": stmt.bank_account.currency,
            "reference": stmt.reference,
            "start": stmt.start,
            "end": stmt.end,
            "opening_balance": stmt.opening_balance,
            "closing_balance": stmt.closing_balance,
            "is_complete": obj.is_complete,
            "evidence": obj.evidence,
            "summary": services.reconciliation_summary(obj),
            "lines": lines,
            "ledger": s.BankLineSerializer(services.ledger_unmatched(obj), many=True).data,
        }
    )


@extend_schema(tags=["banking"])
class BankViewSet(FinanceViewSet):
    serializer_class = s.BankSerializer
    queryset = BankAccount.objects.all()

    def list(self, request):
        qs = self.queryset.all()
        if request.query_params.get("search"):
            qs = qs.filter(name__icontains=request.query_params["search"])
        return self.respond_list(qs)

    def retrieve(self, request, pk=None):
        return Response(
            self.serializer_class(
                self.get_object(), context={"request": request, "detail": True}
            ).data
        )

    @extend_schema(request=s.BankInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                services.save_account(request, validated(s.BankInput, request.data))
            ).data,
            status=201,
        )

    @extend_schema(request=s.BankInput)
    def partial_update(self, request, pk=None):
        return Response(
            self.serializer_class(
                services.save_account(
                    request, validated(s.BankInput, request.data, partial=True), pk
                )
            ).data
        )


@extend_schema(tags=["banking"])
class TransactionViewSet(FinanceViewSet):
    serializer_class = s.BankLineSerializer
    queryset = (
        JournalLine.objects.filter(journal__status="posted", account__bank_account__isnull=False)
        .select_related("account", "journal")
        .order_by("-journal__posting_date", "-pk")
    )

    def list(self, request):
        qs = self.queryset.all()
        if request.query_params.get("bank"):
            qs = qs.filter(
                account__bank_account__pk=serializers.IntegerField(min_value=1).run_validation(
                    request.query_params["bank"]
                )
            )
        if request.query_params.get("search"):
            q = request.query_params["search"]
            qs = qs.filter(
                Q(description__icontains=q)
                | Q(journal__description__icontains=q)
                | Q(journal__number__icontains=q)
            )
        if request.query_params.get("from") or request.query_params.get("to"):
            start, end = dates(request)
            qs = qs.filter(journal__posting_date__range=(start, end))
        return self.respond_list(qs)

    @extend_schema(request=s.TreasuryInput, responses=JournalSerializer)
    def create(self, request):
        obj = services.treasury(request, validated(s.TreasuryInput, request.data))
        return Response(JournalSerializer(obj).data, status=201)

    @extend_schema(request=s.TreasuryInput, responses=EnvelopeSerializer)
    @action(detail=False, methods=["post"])
    def preview(self, request):
        return Response(
            services.treasury(request, validated(s.TreasuryInput, request.data), preview=True)
        )


@extend_schema(tags=["reconciliation"], responses=EnvelopeSerializer)
class ReconciliationViewSet(FinanceViewSet):
    serializer_class = EnvelopeSerializer
    queryset = Reconciliation.objects.select_related("statement__bank_account").order_by("-pk")

    def list(self, request):
        qs = self.queryset.all()
        if request.query_params.get("bank"):
            qs = qs.filter(
                statement__bank_account_id=serializers.IntegerField(min_value=1).run_validation(
                    request.query_params["bank"]
                )
            )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response([reconciliation_data(o) for o in page])

    def retrieve(self, request, pk=None):
        return Response(reconciliation_data(self.get_object()))

    @extend_schema(request=s.StatementInput)
    def create(self, request):
        return Response(
            reconciliation_data(
                services.create_statement(request, validated(s.StatementInput, request.data))
            ),
            status=201,
        )

    @extend_schema(request=s.MatchInput)
    @action(detail=True, methods=["post"])
    def match(self, request, pk=None):
        self.get_object()
        data = validated(s.MatchInput, request.data)
        group = services.match(request, pk, data["statement_ids"], data["ledger_ids"])
        return Response({"match_group_id": group.pk})

    @extend_schema(request=EnvelopeSerializer)
    @action(detail=True, methods=["post"])
    def unmatch(self, request, pk=None):
        obj = self.get_object()
        group = get_object_or_404(obj.matches, pk=request.data.get("match_group_id"))
        services.unmatch(request, group.pk)
        return Response({"unmatched": True})

    @extend_schema(request=None)
    @action(detail=True, methods=["post"], url_path="auto-match")
    def auto_match(self, request, pk=None):
        self.get_object()
        return Response({"matched": services.auto_match(request, pk)})

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        self.get_object()
        return Response(reconciliation_data(services.complete(request, pk)))

    @extend_schema(request=DecisionInput)
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        self.get_object()
        return Response(
            reconciliation_data(
                services.complete(
                    request,
                    pk,
                    reopen=True,
                    reason=validated(DecisionInput, request.data)["reason"],
                )
            )
        )


@extend_schema(tags=["banking"], responses=EnvelopeSerializer)
class OverviewView(FinanceView):
    def get(self, request):
        today = timezone.localdate()
        start = today.replace(day=1)
        banks = list(BankAccount.objects.all())
        bank_rows = s.BankSerializer(banks, many=True).data
        cf = reports.report("cf", start, today)
        tb = reports.report("tb", date.min, today)
        months = []
        for m in range(1, today.month + 1):
            import calendar

            end = min(date(today.year, m, calendar.monthrange(today.year, m)[1]), today)
            snapshot = reports.report("cf", date(today.year, 1, 1), end)
            positions = {row["account_id"]: row["raw_balance"] for row in snapshot["rows"]}
            months.append(
                {
                    "month": end.strftime("%b"),
                    "balance": snapshot["closing"],
                    "accounts": {str(b.pk): positions.get(b.gl_account_id, "0") for b in banks},
                }
            )
        return Response(
            {
                "accounts": bank_rows,
                "cash_movement": cf,
                "trial_balance": {"balanced": tb["balanced"], "total": tb["total_debits"]},
                "open_periods": AccountingPeriod.objects.filter(
                    is_closed=False, start__lte=today
                ).count(),
                "unmatched_statement": sum(
                    r["summary"]["unmatched_statement"]
                    for r in [
                        reconciliation_data(o)
                        for o in Reconciliation.objects.filter(is_complete=False).select_related(
                            "statement__bank_account"
                        )
                    ]
                ),
                "months": months,
            }
        )
