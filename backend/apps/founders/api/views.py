from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import (
    IsActiveUser,
    get_permission_codes,
    require,
    requires,
    requires_any,
)
from apps.company.models import FinancialParty
from apps.core.exceptions import BusinessRuleViolation
from apps.core.exporting import csv_response
from apps.core.pagination import StandardPagination
from apps.files.access import can_read
from apps.sales.api.base import search, sort, validated

from .. import models as m
from ..services import common, corporate, evidence, planning, reports, sharing
from . import serializers as s


class FounderViewSet(viewsets.GenericViewSet):
    permission_classes = [IsActiveUser, requires("founder.view")]
    pagination_class = StandardPagination
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        common.enabled()
        qs = self.queryset.all()
        for key in ("party_id", "status", "currency", "kind", "classification"):
            if key in self.request.query_params and key.removesuffix("_id") in {
                f.name for f in qs.model._meta.fields
            }:
                value = self.request.query_params[key]
                if key.endswith("_id"):
                    value = serializers.IntegerField(min_value=1).run_validation(value)
                qs = qs.filter(**{key: value})
        return qs

    def list(self, request):
        qs = self.get_queryset()
        fields = {f.name for f in qs.model._meta.fields}
        qs = search(
            qs,
            request,
            *[f for f in ("name", "title", "reference", "description", "notes") if f in fields],
        )
        qs = sort(
            qs,
            request,
            fields & {"id", "name", "date", "amount", "status", "created_at", "effective_from"},
            "-id",
        )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(
            self.serializer_class(page, many=True, context={"request": request}).data
        )

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object(), context={"request": request}).data)


@extend_schema(tags=["founders"])
class PartyViewSet(FounderViewSet):
    permission_classes = [
        IsActiveUser,
        requires_any(
            "founder.view",
            "ownership.view",
            "ownership.manage",
            "founder.personal.view",
            "ownership.consent",
        ),
    ]
    serializer_class = s.PartySerializer
    queryset = FinancialParty.objects.all()

    def get_queryset(self):
        qs = self.queryset.all()
        codes = get_permission_codes(self.request.user)
        if {"founder.view", "ownership.view", "ownership.manage"} & codes:
            return qs
        # Participants can identify themselves and the counterparties in their
        # own records, without receiving the full corporate party directory.
        from apps.ownership.models import OwnershipProposal

        linked = FinancialParty.objects.filter(user=self.request.user).first()
        allowed = {linked.pk} if linked else set()
        if linked:
            for settlement in sharing.visible_settlements(self.request.user):
                allowed.update([settlement.payer_id, settlement.recipient_id])
            for proposal in OwnershipProposal.objects.all():
                if linked.pk in proposal.snapshot.get("required_parties", []):
                    allowed.update(proposal.snapshot["required_parties"])
        return qs.filter(pk__in=allowed)

    @extend_schema(request=s.PartyInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                common.save_party(request, validated(s.PartyInput, request.data))
            ).data,
            status=201,
        )

    @extend_schema(request=s.PartyInput)
    def partial_update(self, request, pk=None):
        self.get_object()
        return Response(
            self.serializer_class(
                common.save_party(request, validated(s.PartyInput, request.data, partial=True), pk)
            ).data
        )


@extend_schema(tags=["founders"])
class LoanViewSet(FounderViewSet):
    serializer_class = s.LoanSerializer
    queryset = m.FounderLoan.objects.all()

    @extend_schema(request=s.LoanInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                corporate.save_loan(request, validated(s.LoanInput, request.data))
            ).data,
            status=201,
        )


@extend_schema(tags=["founders"])
class CorporateViewSet(FounderViewSet):
    serializer_class = s.CorporateSerializer
    queryset = m.CorporateTransaction.objects.select_related("party")

    @extend_schema(request=s.CorporateInput)
    def create(self, request):
        data = validated(s.CorporateInput, request.data)
        key = data.pop("client_key")
        return Response(
            self.serializer_class(corporate.record_transaction(request, data, key)).data, status=201
        )

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        self.get_object()
        return Response(corporate.preview(request, pk))

    @extend_schema(request=s.QuoteInput)
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        self.get_object()
        return Response(
            self.serializer_class(
                corporate.verify(request, pk, validated(s.QuoteInput, request.data))
            ).data
        )

    @extend_schema(request=s.ReasonInput)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        self.get_object()
        return Response(
            self.serializer_class(
                corporate.reject(request, pk, validated(s.ReasonInput, request.data)["reason"])
            ).data
        )

    @extend_schema(request=s.ReasonInput)
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        self.get_object()
        data = validated(s.ReasonInput, request.data)
        return Response(
            self.serializer_class(
                corporate.reverse(
                    request, pk, data.get("date", timezone.localdate()), data["reason"]
                )
            ).data
        )


@extend_schema(tags=["founders"])
class PolicyViewSet(FounderViewSet):
    serializer_class = s.PolicySerializer
    queryset = m.SharingPolicy.objects.all()

    @extend_schema(request=s.PolicyInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                sharing.save_policy(request, validated(s.PolicyInput, request.data))
            ).data,
            status=201,
        )

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        self.get_object()
        return Response(self.serializer_class(sharing.activate(request, pk)).data)


@extend_schema(tags=["personal-sharing"])
class SharingViewSet(FounderViewSet):
    permission_classes = [IsActiveUser, requires("founder.personal.view")]
    serializer_class = s.SharedExpenseSerializer
    queryset = m.SharedExpense.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        if "founder.attest" not in get_permission_codes(self.request.user):
            qs = qs.filter(
                Q(payer__user=self.request.user) | Q(obligations__debtor__user=self.request.user)
            ).distinct()
        return qs

    @extend_schema(request=s.SharedExpenseInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                sharing.allocate_expense(request, validated(s.SharedExpenseInput, request.data))
            ).data,
            status=201,
        )


@extend_schema(tags=["personal-sharing"])
class PersonalViewSet(FounderViewSet):
    permission_classes = [IsActiveUser, requires("founder.personal.view")]
    serializer_class = s.PersonalSerializer
    queryset = m.PersonalSettlement.objects.all()

    def get_queryset(self):
        common.enabled()
        return sharing.visible_settlements(self.request.user)

    @extend_schema(request=s.PersonalInput)
    def create(self, request):
        data = validated(s.PersonalInput, request.data)
        key = data.pop("client_key")
        return Response(
            self.serializer_class(sharing.record_settlement(request, data, key)).data, status=201
        )

    @extend_schema(request=s.ConfirmationInput)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        self.get_object()
        data = validated(s.ConfirmationInput, request.data)
        return Response(self.serializer_class(sharing.confirm_settlement(request, pk, **data)).data)

    @extend_schema(request=s.ReasonInput)
    @action(detail=True, methods=["post"])
    def dispute(self, request, pk=None):
        self.get_object()
        return Response(
            self.serializer_class(
                sharing.dispute(request, pk, validated(s.ReasonInput, request.data)["reason"])
            ).data
        )


@extend_schema(tags=["founder-planning"])
class PlanViewSet(FounderViewSet):
    permission_classes = [IsActiveUser, requires("founder.planning.manage")]
    serializer_class = s.PlanSerializer
    queryset = m.FundingPlan.objects.all()

    @extend_schema(request=s.ForecastInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                planning.forecast(request, validated(s.ForecastInput, request.data), save=True)
            ).data,
            status=201,
        )

    @extend_schema(request=s.ForecastInput, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def preview(self, request):
        return Response(planning.forecast(request, validated(s.ForecastInput, request.data)))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        return Response(planning.progress(request, self.get_object()))


@extend_schema(tags=["founder-planning"])
class ReserveViewSet(FounderViewSet):
    permission_classes = [IsActiveUser, requires("founder.planning.manage")]
    serializer_class = s.ReserveSerializer
    queryset = m.AnnualReserve.objects.all()

    @extend_schema(request=s.ReserveInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                planning.save_reserve(request, validated(s.ReserveInput, request.data))
            ).data,
            status=201,
        )


@extend_schema(tags=["founder-planning"])
class CompanyCoverageViewSet(FounderViewSet):
    permission_classes = [IsActiveUser, requires("founder.planning.manage")]
    serializer_class = s.CompanyCoverageSerializer
    queryset = m.CompanyFundingCoverage.objects.all()

    @extend_schema(request=s.CompanyCoverageInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                planning.cover_from_company(
                    request, validated(s.CompanyCoverageInput, request.data)
                )
            ).data,
            status=201,
        )

    @extend_schema(request=s.CoverageDecisionInput)
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        self.get_object()
        return Response(
            self.serializer_class(
                planning.update_company_coverage(
                    request, pk, validated(s.CoverageDecisionInput, request.data)
                )
            ).data
        )


@extend_schema(tags=["founder-planning"])
class DesignationViewSet(FounderViewSet):
    permission_classes = [IsActiveUser, requires("founder.planning.manage")]
    serializer_class = s.DesignationSerializer
    queryset = m.FundingDesignation.objects.all()

    @extend_schema(request=s.ReleaseInput)
    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        self.get_object()
        data = validated(s.ReleaseInput, request.data)
        planning.release_funding(request, pk, **data)
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=s.DesignationInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                planning.designate(request, validated(s.DesignationInput, request.data))
            ).data,
            status=201,
        )

    @extend_schema(request=s.ConsumeInput)
    @action(detail=True, methods=["post"])
    def consume(self, request, pk=None):
        self.get_object()
        return Response(
            self.serializer_class(
                planning.consume(request, pk, **validated(s.ConsumeInput, request.data))
            ).data
        )


@extend_schema(tags=["founder-planning"])
class PledgeViewSet(FounderViewSet):
    permission_classes = [IsActiveUser, requires("founder.planning.manage")]
    serializer_class = s.PledgeSerializer
    queryset = m.FundingPledge.objects.all()

    @extend_schema(request=s.PledgeStatusInput)
    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        self.get_object()
        data = validated(s.PledgeStatusInput, request.data)
        return Response(
            self.serializer_class(
                planning.pledge_status(request, pk, data["status"], data["reason"])
            ).data
        )

    @extend_schema(request=s.PledgeInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                planning.pledge(request, validated(s.PledgeInput, request.data))
            ).data,
            status=201,
        )


@extend_schema(tags=["founder-planning"])
class ConsumptionViewSet(FounderViewSet):
    permission_classes = [IsActiveUser, requires("founder.planning.manage")]
    serializer_class = s.ConsumptionSerializer
    queryset = m.FundingConsumption.objects.all()

    @extend_schema(request=s.ReasonInput)
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        self.get_object()
        return Response(
            self.serializer_class(
                planning.reverse_consumption(
                    request, pk, validated(s.ReasonInput, request.data)["reason"]
                )
            ).data
        )


@extend_schema(tags=["founders"])
class ResolutionViewSet(FounderViewSet):
    serializer_class = s.ResolutionSerializer
    queryset = m.RecoveryResolution.objects.all()

    @extend_schema(request=s.ResolutionInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                corporate.resolve_recovery(request, validated(s.ResolutionInput, request.data))
            ).data,
            status=201,
        )


@extend_schema(tags=["founder-evidence"])
class EvidenceViewSet(FounderViewSet):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsActiveUser]
    serializer_class = s.EvidenceSerializer
    queryset = m.FounderEvidence.objects.select_related("file")

    def get_queryset(self):
        # Exclude unauthorized rows before pagination/counting.
        ids = [obj.pk for obj in self.queryset if can_read(self.request.user, obj.file)]
        qs = self.queryset.filter(pk__in=ids)
        for key in ("transaction_id", "settlement_id", "loan_id", "party_id"):
            if key in self.request.query_params:
                qs = qs.filter(
                    **{
                        key: serializers.IntegerField(min_value=1).run_validation(
                            self.request.query_params[key]
                        )
                    }
                )
        return qs

    @extend_schema(request=s.EvidenceInput)
    def create(self, request):
        data = validated(s.EvidenceInput, request.data)
        file = data.pop("file")
        obj = evidence.upload(request, data, file)
        if data.get("proposal_id"):
            from apps.ownership.api.serializers import EvidenceSerializer

            return Response(EvidenceSerializer(obj).data, status=201)
        return Response(self.serializer_class(obj).data, status=201)


@extend_schema(tags=["founders"])
class OverviewView(APIView):
    permission_classes = [IsActiveUser, requires("founder.view")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        common.enabled()
        pk = (
            serializers.IntegerField(min_value=1).run_validation(request.query_params["party_id"])
            if "party_id" in request.query_params
            else None
        )
        return Response(reports.overview(request, pk))


@extend_schema(tags=["founders"])
class ObligationView(APIView):
    permission_classes = [IsActiveUser, requires("founder.view")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        common.enabled()
        qs = (
            m.FounderObligation.objects.filter(origin__status="posted")
            .select_related("party")
            .order_by("pk")
        )
        if "party_id" in request.query_params:
            qs = qs.filter(
                party_id=serializers.IntegerField(min_value=1).run_validation(
                    request.query_params["party_id"]
                )
            )
        pager = StandardPagination()
        return pager.get_paginated_response(
            [reports.obligation_row(obj) for obj in pager.paginate_queryset(qs, request)]
        )


@extend_schema(tags=["personal-sharing"])
class PersonalBalanceView(APIView):
    permission_classes = [IsActiveUser, requires("founder.personal.view")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        common.enabled()
        rows = reports.personal_balance_rows(request.user)
        pager = StandardPagination()
        return pager.get_paginated_response(pager.paginate_queryset(rows, request))


@extend_schema(tags=["founders"])
class StatementView(APIView):
    permission_classes = [IsActiveUser, requires("founder.view")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        common.enabled()
        rows = reports.statement(request)
        if request.query_params.get("export") == "csv":
            require(request.user, "reports.export")
            if len(rows) > 10000:
                raise BusinessRuleViolation(
                    "Narrow the statement dates before exporting over 10,000 rows."
                )
            return csv_response(
                rows,
                name="founder-company-statement",
                columns=[
                    "date",
                    "party",
                    "control",
                    "currency",
                    "debit",
                    "credit",
                    "balance",
                    "base_balance",
                    "number",
                    "description",
                ],
            )
        pager = StandardPagination()
        return pager.get_paginated_response(pager.paginate_queryset(rows, request))
