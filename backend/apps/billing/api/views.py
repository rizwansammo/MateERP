from datetime import date

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

from apps.accounting.models import Account
from apps.accounting.money import ZERO, strings
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import IsActiveUser, require, requires
from apps.audit.services import record
from apps.documents.services import generate_pdf, retry_pdf
from apps.sales.api.base import DomainViewSet, search, sort, validated
from apps.sales.models import Customer, Project

from ..models import (
    CreditNote,
    CustomerCreditMovement,
    CustomerPayment,
    Invoice,
    MoneyReceipt,
    RecurringInvoiceSchedule,
    Refund,
)
from ..services import common, credits, invoices, overview, payments, reconciliation, recurring
from . import serializers as s


def idempotency_key(request, data=None):
    return request.headers.get("Idempotency-Key") or (data or {}).get("posting_key")


@extend_schema(tags=["billing"])
class InvoiceViewSet(DomainViewSet):
    serializer_class = s.InvoiceDetailSerializer
    queryset = Invoice.objects.select_related(
        "customer",
        "project",
        "journal",
        "void_journal",
        "branding_version",
        "created_by",
        "approved_by",
        "issued_by",
    ).prefetch_related("lines")
    write_permissions = ("invoices.create", "invoices.issue", "credit_notes.manage")

    def get_object(self):
        obj = super().get_object()
        return invoices.sync_approval(obj)

    def list(self, request):
        qs = search(
            self.queryset, request, "number", "customer__name", "reference", "project__reference"
        )
        status = request.query_params.get("status")
        today = timezone.localdate()
        if status == "open":
            qs = qs.filter(status__in=("issued", "partially_paid"))
        elif status == "overdue":
            qs = qs.filter(status__in=("issued", "partially_paid"), due_date__lt=today)
        elif status == "draft":
            qs = qs.filter(status__in=("draft", "pending_approval", "approved"))
        elif status:
            qs = qs.filter(status=status)
        for param, field in (("customer", "customer_id"), ("project", "project_id")):
            if request.query_params.get(param):
                qs = qs.filter(**{field: request.query_params[param]})
        qs = sort(qs, request, ("issue_date", "due_date", "number", "total"), "-issue_date")
        return self.respond_list(qs, s.InvoiceListSerializer)

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=s.InvoiceInput)
    def create(self, request):
        obj = invoices.save_invoice(request, validated(s.InvoiceInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.InvoiceInput)
    def partial_update(self, request, pk=None):
        data = validated(s.InvoiceInput, request.data, partial=True)
        return Response(self.serializer_class(invoices.save_invoice(request, data, pk)).data)

    @extend_schema(request=s.FromSourceInput)
    @action(detail=False, methods=["post"], url_path="from-source")
    def from_source(self, request):
        data = validated(s.FromSourceInput, request.data)
        if data.get("order_id"):
            obj = invoices.create_from_order(request, data["order_id"], data)
        elif data.get("milestone_id"):
            obj = invoices.create_from_milestone(request, data["milestone_id"], data)
        else:
            raise NotFound()
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return Response(self.serializer_class(invoices.approve_invoice(request, pk)).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        return Response(self.serializer_class(invoices.issue_and_render(request, pk)).data)

    @extend_schema(request=s.DocumentDecisionInput)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        data = validated(s.DocumentDecisionInput, request.data)
        obj = invoices.void_invoice(request, pk, data["reason"], data.get("date"))
        return Response(self.serializer_class(obj).data)

    @extend_schema(request=s.DocumentDecisionInput)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        data = validated(s.DocumentDecisionInput, request.data)
        return Response(
            self.serializer_class(invoices.cancel_draft(request, pk, data["reason"])).data
        )

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def pdf(self, request, pk=None):
        return Response(self.serializer_class(retry_pdf(request, "invoice", pk)).data)

    @extend_schema(request=s.CreditNoteInput, responses=s.CreditNoteSerializer)
    @action(detail=True, methods=["post"], url_path="credit-notes")
    def credit_note(self, request, pk=None):
        data = validated(s.CreditNoteInput, request.data)
        note = credits.request_credit_note(
            request, int(pk), data, idempotency_key(request, request.data)
        )
        if note.number and note.pdf_status != "ready":
            note = generate_pdf("credit_note", note.pk)
        return Response(s.CreditNoteSerializer(note).data, status=201)


@extend_schema(tags=["billing"])
class PaymentViewSet(DomainViewSet):
    serializer_class = s.PaymentSerializer
    queryset = CustomerPayment.objects.select_related(
        "customer", "bank_account", "recorded_by", "decided_by", "journal", "reversal_journal"
    ).prefetch_related("allocations__invoice")
    write_permissions = ("payments.record", "payments.approve")

    def get_object(self):
        return payments.sync_approval(super().get_object())

    def list(self, request):
        qs = search(self.queryset, request, "number", "reference", "customer__name")
        status = request.query_params.get("status")
        if status == "pending":
            qs = qs.filter(status__in=("pending_verification", "awaiting_approval"))
        elif status:
            qs = qs.filter(status=status)
        if request.query_params.get("customer"):
            qs = qs.filter(customer_id=request.query_params["customer"])
        if request.query_params.get("invoice"):
            qs = qs.filter(allocations__invoice_id=request.query_params["invoice"])
        return self.respond_list(
            sort(qs, request, ("payment_date", "number", "amount"), "-payment_date")
        )

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=s.PaymentInput)
    def create(self, request):
        data = validated(s.PaymentInput, request.data)
        data["allocations"] = [dict(a) for a in data.get("allocations", [])]
        obj = payments.record_payment(request, data, idempotency_key(request, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        return Response(self.serializer_class(payments.verify_and_render(request, pk)).data)

    @extend_schema(request=s.DocumentDecisionInput)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        reason = validated(s.DocumentDecisionInput, request.data)["reason"]
        return Response(self.serializer_class(payments.reject_payment(request, pk, reason)).data)

    @extend_schema(request=s.DocumentDecisionInput)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reason = validated(s.DocumentDecisionInput, request.data)["reason"]
        return Response(self.serializer_class(payments.cancel_payment(request, pk, reason)).data)

    @extend_schema(request=s.DocumentDecisionInput)
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        data = validated(s.DocumentDecisionInput, request.data)
        obj = payments.reverse_payment(request, pk, data["reason"], data.get("date"))
        return Response(self.serializer_class(obj).data)


@extend_schema(tags=["billing"])
class ReceiptViewSet(DomainViewSet):
    serializer_class = s.ReceiptSerializer
    queryset = MoneyReceipt.objects.select_related(
        "payment__customer", "branding_version", "pdf_file"
    )
    write_permissions = ("payments.approve", "documents.manage")

    def list(self, request):
        qs = search(self.queryset, request, "number", "payment__number", "payment__customer__name")
        if request.query_params.get("customer"):
            qs = qs.filter(payment__customer_id=request.query_params["customer"])
        if request.query_params.get("invoice"):
            qs = qs.filter(payment__allocations__invoice_id=request.query_params["invoice"])
        return self.respond_list(sort(qs, request, ("issue_date", "number"), "-issue_date"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def pdf(self, request, pk=None):
        return Response(self.serializer_class(retry_pdf(request, "receipt", pk)).data)


@extend_schema(tags=["billing"])
class CreditNoteViewSet(DomainViewSet):
    serializer_class = s.CreditNoteSerializer
    queryset = CreditNote.objects.select_related("invoice", "customer", "journal", "pdf_file")
    write_permissions = ("credit_notes.manage",)

    def get_object(self):
        return credits.sync_credit_note(super().get_object())

    def list(self, request):
        qs = search(self.queryset, request, "number", "invoice__number", "customer__name", "reason")
        if request.query_params.get("customer"):
            qs = qs.filter(customer_id=request.query_params["customer"])
        if request.query_params.get("invoice"):
            qs = qs.filter(invoice_id=request.query_params["invoice"])
        return self.respond_list(sort(qs, request, ("issue_date", "number"), "-issue_date"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def pdf(self, request, pk=None):
        return Response(self.serializer_class(retry_pdf(request, "credit_note", pk)).data)


@extend_schema(tags=["billing"])
class RefundViewSet(DomainViewSet):
    serializer_class = s.RefundSerializer
    queryset = Refund.objects.select_related("customer", "bank_account", "journal")
    write_permissions = ("credit_notes.manage",)

    def get_object(self):
        return credits.sync_refund(super().get_object())

    def list(self, request):
        qs = search(self.queryset, request, "number", "customer__name", "reason")
        if request.query_params.get("customer"):
            qs = qs.filter(customer_id=request.query_params["customer"])
        return self.respond_list(sort(qs, request, ("refund_date", "number"), "-refund_date"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=s.RefundInput)
    def create(self, request):
        data = validated(s.RefundInput, request.data)
        obj = credits.request_refund(request, data, idempotency_key(request, request.data))
        return Response(self.serializer_class(obj).data, status=201)


@extend_schema(tags=["billing"], request=s.ApplicationInput, responses=s.ApplicationSerializer)
class CreditApplicationView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view", "payments.record")]

    def post(self, request):
        data = validated(s.ApplicationInput, request.data)
        obj = credits.apply_credit(request, data, idempotency_key(request, request.data))
        return Response(s.ApplicationSerializer(obj).data, status=201)


@extend_schema(tags=["billing"])
class ScheduleViewSet(DomainViewSet):
    serializer_class = s.ScheduleSerializer
    queryset = RecurringInvoiceSchedule.objects.select_related(
        "customer", "auto_issue_authorized_by"
    )
    write_permissions = ("invoices.create",)

    def list(self, request):
        qs = search(self.queryset, request, "name", "customer__name")
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return self.respond_list(sort(qs, request, ("name", "next_run_date"), "name"))

    def retrieve(self, request, pk=None):
        schedule = self.get_object()
        data = self.serializer_class(schedule).data
        data["runs"] = s.RunSerializer(schedule.runs.select_related("invoice")[:50], many=True).data
        data["due"] = recurring.due_occurrences(schedule, timezone.localdate())
        return Response(data)

    @extend_schema(request=s.ScheduleInput)
    def create(self, request):
        obj = recurring.save_schedule(request, validated(s.ScheduleInput, request.data))
        return Response(self.serializer_class(obj).data, status=201)

    @extend_schema(request=s.ScheduleInput)
    def partial_update(self, request, pk=None):
        data = validated(s.ScheduleInput, request.data, partial=True)
        return Response(self.serializer_class(recurring.save_schedule(request, data, pk)).data)

    @extend_schema(request=s.StatusInput)
    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        status = validated(s.StatusInput, request.data)["status"]
        return Response(self.serializer_class(recurring.set_status(request, pk, status)).data)

    @extend_schema(request=None, responses=s.RunSerializer(many=True))
    @action(detail=False, methods=["get"])
    def preview(self, request):
        until = request.query_params.get("until")
        until = date.fromisoformat(until) if until else timezone.localdate()
        return Response(
            [
                {
                    "schedule_id": row["schedule"].pk,
                    "name": row["schedule"].name,
                    "dates": row["dates"],
                }
                for row in recurring.preview(until)
                if row["dates"]
            ]
        )

    @extend_schema(request=s.RunInput, responses=s.RunSerializer(many=True))
    @action(detail=False, methods=["post"])
    def run(self, request):
        data = validated(s.RunInput, request.data)
        results = recurring.run_due(
            data.get("until"), runner=request.user, schedule_ids=data.get("schedule_ids")
        )
        record("billing.recurring_run", request=request, after={"occurrences": len(results)})
        return Response(strings(results))


@extend_schema(tags=["billing"], responses=OpenApiTypes.OBJECT)
class ReconciliationView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request):
        result = reconciliation.receivables()
        for value in result.values():
            account = value.pop("account")
            value["account"] = (
                {"id": account.pk, "code": account.code, "name": account.name} if account else None
            )
        return Response(strings(result))


@extend_schema(tags=["billing"], responses=OpenApiTypes.OBJECT)
class OverviewView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    @transaction.atomic
    def get(self, request):
        company = lock_company()
        today = timezone.localdate()
        base = common.base_currency()
        open_qs = Invoice.objects.filter(
            status__in=("issued", "partially_paid"), issue_date__lte=today
        )
        base_open = open_qs.aggregate(t=Sum("base_total"), s=Sum("base_settled"))
        overdue = open_qs.filter(due_date__lt=today).aggregate(
            t=Sum("base_total"), s=Sum("base_settled")
        )
        return Response(
            strings(
                {
                    "base_currency": base,
                    "outstanding": (base_open["t"] or ZERO) - (base_open["s"] or ZERO),
                    "overdue": (overdue["t"] or ZERO) - (overdue["s"] or ZERO),
                    "overdue_count": open_qs.filter(due_date__lt=today).count(),
                    "open_count": open_qs.count(),
                    "pending_verification": CustomerPayment.objects.filter(
                        status__in=("pending_verification", "awaiting_approval")
                    ).count(),
                    "drafts": Invoice.objects.filter(
                        status__in=("draft", "pending_approval", "approved")
                    ).count(),
                    **overview.sales(company, today),
                }
            )
        )


@extend_schema(tags=["billing"], responses=OpenApiTypes.OBJECT)
class CustomerAccountView(APIView):
    """Customer balances, credit and a running statement in each currency."""

    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request, pk):
        customer = Customer.objects.filter(pk=pk).first()
        if customer is None:
            raise NotFound()
        events = []
        for inv in Invoice.objects.filter(customer=customer, number__isnull=False).order_by(
            "issue_date", "pk"
        ):
            events.append(
                (
                    inv.issue_date,
                    inv.currency,
                    "Invoice",
                    inv.number,
                    inv.total,
                    ZERO,
                    f"invoice:{inv.pk}",
                )
            )
            if inv.status == "void":
                events.append(
                    (
                        inv.voided_at.date(),
                        inv.currency,
                        "Void",
                        inv.number,
                        ZERO,
                        inv.total,
                        f"invoice:{inv.pk}",
                    )
                )
        for pay in CustomerPayment.objects.filter(
            customer=customer, status__in=("verified", "reversed")
        ):
            events.append(
                (
                    pay.payment_date,
                    pay.currency,
                    "Payment",
                    pay.number,
                    ZERO,
                    pay.amount,
                    f"payment:{pay.pk}",
                )
            )
            if pay.status == "reversed":
                events.append(
                    (
                        pay.reversal_journal.posting_date,
                        pay.currency,
                        "Payment reversed",
                        pay.number,
                        pay.amount,
                        ZERO,
                        f"payment:{pay.pk}",
                    )
                )
        for note in CreditNote.objects.filter(customer=customer, status="issued"):
            events.append(
                (
                    note.issue_date,
                    note.currency,
                    "Credit note",
                    note.number,
                    ZERO,
                    note.total,
                    f"credit_note:{note.pk}",
                )
            )
        for refund in Refund.objects.filter(customer=customer, status="paid"):
            events.append(
                (
                    refund.refund_date,
                    refund.currency,
                    "Refund",
                    refund.number,
                    refund.amount,
                    ZERO,
                    f"refund:{refund.pk}",
                )
            )
        events.sort(key=lambda e: (e[0], e[3]))
        running, statement = {}, []
        for on, currency, kind, number, debit, credit, ref in events:
            running[currency] = running.get(currency, ZERO) + debit - credit
            statement.append(
                {
                    "date": on,
                    "currency": currency,
                    "kind": kind,
                    "number": number,
                    "debit": debit,
                    "credit": credit,
                    "balance": running[currency],
                    "ref": ref,
                }
            )
        balances = reconciliation.customer_balances([customer.pk]).get(customer.pk, {})
        credit = (
            CustomerCreditMovement.objects.filter(customer=customer)
            .values("currency")
            .annotate(n=Sum("amount"))
            .order_by()
        )
        return Response(
            strings(
                {
                    "balances": [{"currency": k, **v} for k, v in balances.items()],
                    "credit": [
                        {"currency": r["currency"], "amount": r["n"]} for r in credit if r["n"]
                    ],
                    "statement": statement,
                }
            )
        )


@extend_schema(
    tags=["billing"],
    responses=inline_serializer(
        "CustomerBalanceRow",
        {"customer_id": serializers.IntegerField(), "balances": serializers.DictField()},
        many=True,
    ),
)
class CustomerBalancesView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request):
        data = reconciliation.customer_balances()
        return Response(strings([{"customer_id": k, "balances": v} for k, v in data.items()]))


@extend_schema(tags=["billing"], responses=OpenApiTypes.OBJECT)
class ProjectFinancialsView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    @transaction.atomic
    def get(self, request, pk):
        lock_company()
        project = Project.objects.select_related("customer").filter(pk=pk).first()
        if project is None:
            raise NotFound()
        issued = Invoice.objects.filter(project=project, number__isnull=False).exclude(
            status="void"
        )
        totals = issued.aggregate(
            invoiced=Sum("total"),
            paid=Sum("amount_paid"),
            credited=Sum("amount_credited"),
            net_revenue=Sum("taxable"),
        )
        from apps.purchasing.services.selectors import project_costs

        costs = project_costs(project)
        invoiced = (totals["invoiced"] or ZERO) - (totals["credited"] or ZERO)
        credited_revenue = (
            CreditNote.objects.filter(invoice__project=project, status="issued").aggregate(
                total=Sum("taxable")
            )["total"]
            or ZERO
        )
        net_invoiced = (totals["net_revenue"] or ZERO) - credited_revenue
        from apps.company.models import CompanyProfile
        from apps.reporting.attribution import project_revenue

        base_revenue, net_revenue = project_revenue(project)
        milestones = []
        for m in project.milestones.all():
            inv = (
                Invoice.objects.filter(milestone=m)
                .exclude(status__in=("void", "cancelled"))
                .first()
            )
            milestones.append(
                {
                    "id": m.pk,
                    "name": m.name,
                    "percent": m.percent,
                    "amount": m.amount,
                    "invoice": {"id": inv.pk, "number": inv.number, "status": inv.status}
                    if inv
                    else None,
                }
            )
        return Response(
            strings(
                {
                    "contract_value": project.contract_value,
                    "currency": project.currency,
                    "invoiced": invoiced,
                    "net_revenue": net_revenue,
                    "collected": totals["paid"] or ZERO,
                    "outstanding": invoiced - (totals["paid"] or ZERO),
                    "uninvoiced": max(project.contract_value - net_invoiced, ZERO),
                    "costs": costs["total"],
                    "cost_lines": costs["lines"],
                    "margin": net_revenue - costs["total"]
                    if net_revenue is not None and costs["total"] is not None
                    else None,
                    "base_currency": CompanyProfile.objects.get().base_currency,
                    "base_revenue": base_revenue,
                    "base_costs": costs["base_total"],
                    "base_margin": base_revenue - costs["base_total"],
                    "milestones": milestones,
                    "note": "Profitability uses source-owned posted GL values, including control "
                    "transfer, returns, asset reclassification and depreciation. Recoverable tax "
                    "and asset cost are excluded from expenses. Base margin includes every source "
                    "currency; native margin is unavailable when currencies differ. Contract, "
                    "invoicing and collections retain their own meanings and project currency. "
                    "Analytical project reclassification does not rewrite financial "
                    "source identity.",
                }
            )
        )


@extend_schema(
    tags=["billing"], request=s.LedgerSettingsSerializer, responses=s.LedgerSettingsSerializer
)
class LedgerSettingsView(APIView):
    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request):
        obj = common.ledger_settings()
        data = s.LedgerSettingsSerializer(obj).data
        data["controls"] = {
            purpose: _account(Account.objects.filter(control=purpose).first())
            for purpose in ("receivable", "payable", "customer_credit", "fx_gain", "fx_loss")
        }
        return Response(data)

    def put(self, request):
        require(request.user, "accounting.manage")
        data = validated(s.LedgerSettingsSerializer, request.data)
        obj = common.ledger_settings()
        for field, kind in (
            ("default_revenue_account_id", "revenue"),
            ("default_expense_account_id", "expense"),
        ):
            if field in data:
                if data[field]:
                    common.posting_account(data[field], kind=kind)
                setattr(obj, field, data[field])
        obj.updated_by = request.user
        obj.save()
        record("billing.ledger_settings_updated", request=request, target=obj, after=data)
        return self.get(request)


def _account(account):
    return {"id": account.pk, "code": account.code, "name": account.name} if account else None


@extend_schema(tags=["billing"], responses=OpenApiTypes.OBJECT)
class DocumentBrandingView(APIView):
    """Layout of a published branding version for on-screen document previews.

    Finance users see the layout, company identity and logo. Signature and seal
    images remain restricted to branding managers; the official PDF, rendered by
    the server, carries them.
    """

    permission_classes = [IsActiveUser, requires("finance.view")]

    def get(self, request):
        from apps.accounts.authorization import get_permission_codes
        from apps.branding.models import BrandingVersion
        from apps.branding.services import current_version
        from apps.files.api.serializers import file_url

        number = request.query_params.get("version")
        version = (
            BrandingVersion.objects.filter(number=number).first()
            if number and number.isdigit()
            else current_version()
        )
        if version is None:
            return Response({"version": None})
        full = "branding.manage" in get_permission_codes(request.user)
        return Response(
            {
                "version": version.number,
                "label": version.label,
                "config": version.config,
                "company": common.company_identity(),
                "logo_url": file_url(version.logo),
                "signature_url": file_url(version.signature) if full else None,
                "seal_image_url": file_url(version.seal_image) if full else None,
            }
        )
