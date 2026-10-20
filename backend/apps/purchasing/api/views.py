from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.money import ZERO, strings
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import IsActiveUser, requires
from apps.audit.services import record
from apps.billing.api.serializers import DocumentDecisionInput, RunInput, StatusInput
from apps.billing.api.views import idempotency_key
from apps.billing.services import common, overview
from apps.sales.api.base import DomainViewSet, search, sort, validated

from ..models import Expense, RecurringExpenseSchedule, Vendor, VendorBill, VendorPayment
from ..services import payables, payments, reconciliation, recurring
from . import serializers as s


def _filter(qs, request, *pairs):
    for param, field in pairs:
        if request.query_params.get(param):
            qs = qs.filter(**{field: request.query_params[param]})
    return qs


@extend_schema(tags=["purchasing"])
class VendorViewSet(DomainViewSet):
    serializer_class = s.VendorSerializer
    queryset = Vendor.objects.all()
    write_permissions = ("vendors.manage",)

    def list(self, request):
        qs = search(self.queryset, request, "name", "code", "email", "contact_name")
        status = request.query_params.get("status")
        if status in ("active", "inactive"):
            qs = qs.filter(is_active=status == "active")
        page = self.paginate_queryset(sort(qs, request, ("name", "code", "created_at"), "name"))
        balances = reconciliation.vendor_balances([v.pk for v in page])
        data = self.serializer_class(page, many=True).data
        for row in data:
            row["balances"] = strings(balances.get(row["id"], {}))
        return self.get_paginated_response(data)

    def retrieve(self, request, pk=None):
        vendor = self.get_object()
        data = self.serializer_class(vendor).data
        data["balances"] = strings(reconciliation.vendor_balances([vendor.pk]).get(vendor.pk, {}))
        data["spend"] = strings(
            Expense.objects.filter(
                vendor=vendor, status__in=("posted", "partially_paid", "paid")
            ).aggregate(t=Sum("base_total"))["t"]
            or ZERO
        )
        return Response(data)

    def create(self, request):
        obj = payables.save_vendor(request, validated(self.serializer_class, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    def partial_update(self, request, pk=None):
        data = validated(self.serializer_class, request.data, partial=True)
        return Response(self.serializer_class(payables.save_vendor(request, data, pk)).data)


@extend_schema(tags=["purchasing"])
class BillViewSet(DomainViewSet):
    serializer_class = s.BillSerializer
    queryset = VendorBill.objects.select_related(
        "vendor", "journal", "void_journal", "created_by"
    ).prefetch_related("lines")
    write_permissions = ("bills.manage",)

    def get_object(self):
        return payables._sync(super().get_object())

    def list(self, request):
        qs = search(self.queryset, request, "number", "vendor_reference", "vendor__name")
        status = request.query_params.get("status")
        if status == "open":
            qs = qs.filter(status__in=("posted", "partially_paid"))
        elif status == "overdue":
            qs = qs.filter(
                status__in=("posted", "partially_paid"), due_date__lt=timezone.localdate()
            )
        elif status:
            qs = qs.filter(status=status)
        qs = _filter(qs, request, ("vendor", "vendor_id"), ("project", "project_id"))
        return self.respond_list(
            sort(qs, request, ("bill_date", "due_date", "number", "total"), "-bill_date")
        )

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=s.BillInput)
    def create(self, request):
        obj = payables.save_bill(request, validated(s.BillInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.BillInput)
    def partial_update(self, request, pk=None):
        data = validated(s.BillInput, request.data, partial=True)
        return Response(self.serializer_class(payables.save_bill(request, data, pk)).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        return Response(self.serializer_class(payables.post_bill(request, pk)).data)

    @extend_schema(request=DocumentDecisionInput)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        data = validated(DocumentDecisionInput, request.data)
        return Response(
            self.serializer_class(
                payables.void_bill(request, pk, data["reason"], data.get("date"))
            ).data
        )

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(self.serializer_class(payables.cancel_bill(request, pk)).data)


@extend_schema(tags=["purchasing"])
class ExpenseViewSet(DomainViewSet):
    serializer_class = s.ExpenseSerializer
    queryset = Expense.objects.select_related(
        "vendor", "account", "bank_account", "journal", "void_journal", "created_by"
    )
    write_permissions = ("expenses.manage",)

    def get_object(self):
        return payables._sync(super().get_object())

    def list(self, request):
        qs = search(self.queryset, request, "number", "description", "vendor__name", "reference")
        qs = _filter(
            qs,
            request,
            ("status", "status"),
            ("vendor", "vendor_id"),
            ("mode", "payment_mode"),
            ("project", "project_id"),
        )
        return self.respond_list(
            sort(qs, request, ("expense_date", "number", "total"), "-expense_date")
        )

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=s.ExpenseInput)
    def create(self, request):
        obj = payables.save_expense(request, validated(s.ExpenseInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.ExpenseInput)
    def partial_update(self, request, pk=None):
        data = validated(s.ExpenseInput, request.data, partial=True)
        return Response(self.serializer_class(payables.save_expense(request, data, pk)).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        return Response(self.serializer_class(payables.post_expense(request, pk)).data)

    @extend_schema(request=DocumentDecisionInput)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        data = validated(DocumentDecisionInput, request.data)
        return Response(
            self.serializer_class(
                payables.void_expense(request, pk, data["reason"], data.get("date"))
            ).data
        )

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(self.serializer_class(payables.cancel_expense(request, pk)).data)


@extend_schema(tags=["purchasing"])
class VendorPaymentViewSet(DomainViewSet):
    serializer_class = s.VendorPaymentSerializer
    queryset = VendorPayment.objects.select_related(
        "vendor", "bank_account", "journal", "reversal_journal", "created_by"
    ).prefetch_related("allocations__bill", "allocations__expense")
    write_permissions = ("vendor_payments.manage",)

    def get_object(self):
        return payments.sync_payment(super().get_object())

    def list(self, request):
        qs = search(self.queryset, request, "number", "reference", "vendor__name")
        qs = _filter(
            qs,
            request,
            ("status", "status"),
            ("vendor", "vendor_id"),
            ("bill", "allocations__bill_id"),
        )
        return self.respond_list(
            sort(qs, request, ("payment_date", "number", "amount"), "-payment_date")
        )

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=s.VendorPaymentInput)
    def create(self, request):
        data = validated(s.VendorPaymentInput, request.data)
        data["allocations"] = [dict(a) for a in data["allocations"]]
        obj = payments.pay(request, data, idempotency_key(request, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.VendorPaymentInput)
    @action(detail=False, methods=["post"])
    def preview(self, request):
        data = validated(s.VendorPaymentInput, request.data)
        data["allocations"] = [dict(a) for a in data["allocations"]]
        return Response(payments.preview(request, data))

    @extend_schema(request=DocumentDecisionInput)
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        data = validated(DocumentDecisionInput, request.data)
        return Response(
            self.serializer_class(
                payments.reverse(request, pk, data["reason"], data.get("date"))
            ).data
        )


@extend_schema(tags=["purchasing"])
class ExpenseScheduleViewSet(DomainViewSet):
    serializer_class = s.ExpenseScheduleSerializer
    queryset = RecurringExpenseSchedule.objects.select_related("vendor")
    write_permissions = ("expenses.manage",)

    def list(self, request):
        qs = search(self.queryset, request, "name", "vendor__name")
        qs = _filter(qs, request, ("status", "status"))
        return self.respond_list(sort(qs, request, ("name", "next_run_date"), "name"))

    def retrieve(self, request, pk=None):
        schedule = self.get_object()
        data = self.serializer_class(schedule).data
        data["runs"] = s.ExpenseRunSerializer(
            schedule.runs.select_related("expense")[:50], many=True
        ).data
        data["due"] = recurring.due_occurrences(schedule, timezone.localdate())
        return Response(data)

    @extend_schema(request=s.ExpenseScheduleInput)
    def create(self, request):
        obj = recurring.save_schedule(request, validated(s.ExpenseScheduleInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.ExpenseScheduleInput)
    def partial_update(self, request, pk=None):
        data = validated(s.ExpenseScheduleInput, request.data, partial=True)
        return Response(self.serializer_class(recurring.save_schedule(request, data, pk)).data)

    @extend_schema(request=StatusInput)
    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        status = validated(StatusInput, request.data)["status"]
        return Response(self.serializer_class(recurring.set_status(request, pk, status)).data)

    @extend_schema(request=RunInput)
    @action(detail=False, methods=["post"])
    def run(self, request):
        data = validated(RunInput, request.data)
        results = recurring.run_due(
            data.get("until"), runner=request.user, schedule_ids=data.get("schedule_ids")
        )
        record("purchasing.recurring_run", request=request, after={"occurrences": len(results)})
        return Response(strings(results))

    @extend_schema(request=None)
    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        return Response(self.serializer_class(recurring.upcoming(), many=True).data)


@extend_schema(tags=["purchasing"], responses=OpenApiTypes.OBJECT)
class PayablesReconciliationView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request):
        result = reconciliation.payables()
        account = result.pop("account")
        result["account"] = (
            {"id": account.pk, "code": account.code, "name": account.name} if account else None
        )
        return Response(strings(result))


@extend_schema(tags=["purchasing"], responses=OpenApiTypes.OBJECT)
class PurchasingOverviewView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    @transaction.atomic
    def get(self, request):
        company = lock_company()
        today = timezone.localdate()
        month_start = today.replace(day=1)
        posted = ("posted", "partially_paid", "paid")
        spend = Expense.objects.filter(
            status__in=posted, expense_date__gte=month_start, expense_date__lte=today
        )
        bills_month = VendorBill.objects.filter(
            status__in=posted, bill_date__gte=month_start, bill_date__lte=today
        )
        payables_result = reconciliation.payables()
        open_bills = VendorBill.objects.filter(status__in=("posted", "partially_paid"))
        return Response(
            strings(
                {
                    "base_currency": common.base_currency(),
                    "payables": payables_result["subledger"],
                    "spend_this_month": (spend.aggregate(t=Sum("base_total"))["t"] or ZERO)
                    + (bills_month.aggregate(t=Sum("base_total"))["t"] or ZERO),
                    "open_bills": open_bills.count(),
                    "overdue_bills": open_bills.filter(due_date__lt=today).count(),
                    "drafts": Expense.objects.filter(status="draft").count()
                    + VendorBill.objects.filter(status="draft").count(),
                    "awaiting_approval": Expense.objects.filter(status="awaiting_approval").count()
                    + VendorBill.objects.filter(status="awaiting_approval").count(),
                    "upcoming_renewals": len(recurring.upcoming()),
                    **overview.purchasing(company, today),
                }
            )
        )


@extend_schema(
    tags=["purchasing"],
    responses=inline_serializer(
        "PurchaseHistoryRow",
        {
            "id": serializers.IntegerField(),
            **{
                k: serializers.CharField()
                for k in (
                    "kind",
                    "date",
                    "number",
                    "reference",
                    "party",
                    "status",
                    "currency",
                    "amount",
                )
            },
        },
        many=True,
    ),
)
class PurchaseHistoryView(APIView):
    """Chronological record of bills, expenses and vendor payments (posted and decided)."""

    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 200)), 500)
        vendor = request.query_params.get("vendor")
        rows = []
        bills = VendorBill.objects.exclude(status__in=("draft", "cancelled")).select_related(
            "vendor"
        )
        expenses = Expense.objects.exclude(status__in=("draft", "cancelled")).select_related(
            "vendor"
        )
        pays = VendorPayment.objects.select_related("vendor")
        if vendor:
            bills, expenses, pays = (q.filter(vendor_id=vendor) for q in (bills, expenses, pays))
        for b in bills.order_by("-bill_date")[:limit]:
            rows.append(
                {
                    "kind": "Vendor bill",
                    "id": b.pk,
                    "date": b.bill_date,
                    "number": b.number or "—",
                    "reference": b.vendor_reference,
                    "party": b.vendor.name,
                    "status": b.status,
                    "currency": b.currency,
                    "amount": b.total,
                }
            )
        for e in expenses.order_by("-expense_date")[:limit]:
            rows.append(
                {
                    "kind": "Expense",
                    "id": e.pk,
                    "date": e.expense_date,
                    "number": e.number or "—",
                    "reference": e.description,
                    "party": e.vendor.name if e.vendor else "",
                    "status": e.status,
                    "currency": e.currency,
                    "amount": e.total,
                }
            )
        for p in pays.order_by("-payment_date")[:limit]:
            rows.append(
                {
                    "kind": "Vendor payment",
                    "id": p.pk,
                    "date": p.payment_date,
                    "number": p.number,
                    "reference": p.reference,
                    "party": p.vendor.name,
                    "status": p.status,
                    "currency": p.currency,
                    "amount": p.amount,
                }
            )
        rows.sort(key=lambda r: (r["date"], r["number"]), reverse=True)
        return Response(strings(rows[:limit]))


@extend_schema(
    tags=["purchasing"],
    responses=inline_serializer(
        "VendorStatementRow",
        {
            k: serializers.CharField()
            for k in ("date", "currency", "kind", "number", "debit", "credit", "balance")
        },
        many=True,
    ),
)
class VendorStatementView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request, pk):
        vendor = Vendor.objects.filter(pk=pk).first()
        if vendor is None:
            raise NotFound()
        rows = []
        for b in VendorBill.objects.filter(vendor=vendor, number__isnull=False):
            rows.append((b.bill_date, b.currency, "Bill", b.number, ZERO, b.total))
            if b.status == "void":
                rows.append(
                    (b.void_journal.posting_date, b.currency, "Void", b.number, b.total, ZERO)
                )
        for e in Expense.objects.filter(
            vendor=vendor, payment_mode="accrued", number__isnull=False
        ):
            rows.append((e.expense_date, e.currency, "Accrued expense", e.number, ZERO, e.total))
            if e.status == "void":
                rows.append(
                    (e.void_journal.posting_date, e.currency, "Void", e.number, e.total, ZERO)
                )
        for p in VendorPayment.objects.filter(vendor=vendor, status__in=("paid", "reversed")):
            rows.append((p.payment_date, p.currency, "Payment", p.number, p.amount, ZERO))
            if p.status == "reversed":
                rows.append(
                    (
                        p.reversal_journal.posting_date,
                        p.currency,
                        "Payment reversed",
                        p.number,
                        ZERO,
                        p.amount,
                    )
                )
        rows.sort(key=lambda r: (r[0], r[3]))
        running, out = {}, []
        for on, currency, kind, number, debit, credit in rows:
            running[currency] = running.get(currency, ZERO) + credit - debit
            out.append(
                {
                    "date": on,
                    "currency": currency,
                    "kind": kind,
                    "number": number,
                    "debit": debit,
                    "credit": credit,
                    "balance": running[currency],
                }
            )
        return Response(strings(out))
