from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import IsActiveUser, requires_any
from apps.founders.api.serializers import ConfirmationInput, ReasonInput
from apps.founders.api.views import FounderViewSet
from apps.founders.services.common import enabled, on_date
from apps.founders.services.evidence import can_view_proposal
from apps.founders.services.reports import capital
from apps.sales.api.base import validated

from ..models import OwnershipProposal, ShareClass
from ..services import register
from . import serializers as s


@extend_schema(tags=["ownership"])
class ClassViewSet(FounderViewSet):
    permission_classes = [IsActiveUser, requires_any("ownership.view", "ownership.manage")]
    serializer_class = s.ClassSerializer
    queryset = ShareClass.objects.all()

    def get_queryset(self):
        enabled("ownership")
        return self.queryset.all()

    @extend_schema(request=s.ClassSerializer)
    def create(self, request):
        return Response(
            self.serializer_class(
                register.save_class(request, validated(s.ClassSerializer, request.data))
            ).data,
            status=201,
        )


@extend_schema(tags=["ownership"])
class ProposalViewSet(FounderViewSet):
    permission_classes = [
        IsActiveUser,
        requires_any(
            "ownership.view", "ownership.manage", "ownership.approve", "ownership.consent"
        ),
    ]
    serializer_class = s.ProposalSerializer
    queryset = OwnershipProposal.objects.prefetch_related("lines", "consents", "evidence__file")

    def get_queryset(self):
        enabled("ownership")
        qs = self.queryset.all()
        if self.request.query_params.get("kind"):
            qs = qs.filter(kind=self.request.query_params["kind"])
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        ids = [p.pk for p in qs if can_view_proposal(self.request.user, p)]
        return qs.filter(pk__in=ids)

    @extend_schema(request=s.ProposalInput)
    def create(self, request):
        data = validated(s.ProposalInput, request.data)
        key = data.pop("client_key")
        return Response(
            self.serializer_class(register.propose(request, data, key)).data, status=201
        )

    @extend_schema(request=s.ProposalInput, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def preview(self, request):
        data = validated(s.ProposalInput, request.data)
        data.pop("client_key")
        with transaction.atomic():
            obj = register.propose(request, data, f"preview:{uuid4()}")
            snapshot = obj.snapshot
            transaction.set_rollback(True)
        return Response(s.exact_register_json(snapshot))

    @extend_schema(request=ConfirmationInput)
    @action(detail=True, methods=["post"])
    def consent(self, request, pk=None):
        self.get_object()
        register.consent(request, pk, **validated(ConfirmationInput, request.data))
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        self.get_object()
        return Response(self.serializer_class(register.submit(request, pk)).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        self.get_object()
        return Response(self.serializer_class(register.confirm(request, pk)).data)

    @extend_schema(request=ReasonInput)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        self.get_object()
        return Response(
            self.serializer_class(
                register.cancel(request, pk, validated(ReasonInput, request.data)["reason"])
            ).data
        )


@extend_schema(tags=["ownership"])
class RegisterView(APIView):
    permission_classes = [IsActiveUser, requires_any("ownership.view", "ownership.manage")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        enabled("ownership")
        on = on_date(request.query_params.get("date", timezone.localdate()))
        return Response(
            s.exact_register_json(
                {
                    "date": on,
                    "formal": register.holdings(on),
                    "provisional": register.provisional(on),
                }
            )
        )


@extend_schema(tags=["ownership"])
class CapitalView(APIView):
    permission_classes = [IsActiveUser, requires_any("ownership.view")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        enabled("ownership")
        return Response(s.exact_register_json(capital(request)))
