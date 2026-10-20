from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import IsActiveUser, requires
from apps.approvals import services
from apps.approvals.catalog import CATEGORIES
from apps.approvals.models import ApprovalPolicy, ApprovalRequest

from . import serializers as s


@extend_schema(tags=["approvals"])
class PolicyListView(APIView):
    permission_classes = [IsActiveUser, requires("approvals.manage")]

    @extend_schema(responses=s.ApprovalPolicySerializer(many=True))
    def get(self, request: Request) -> Response:
        order = {c.key: i for i, c in enumerate(CATEGORIES)}
        policies = sorted(
            ApprovalPolicy.objects.select_related("approver_role"),
            key=lambda p: order.get(p.category, 99),
        )
        return Response(s.ApprovalPolicySerializer(policies, many=True).data)


@extend_schema(tags=["approvals"])
class PolicyDetailView(APIView):
    permission_classes = [IsActiveUser, requires("approvals.manage")]

    @extend_schema(request=s.ApprovalPolicyUpdateSerializer, responses=s.ApprovalPolicySerializer)
    def patch(self, request: Request, category: str) -> Response:
        policy = get_object_or_404(ApprovalPolicy, category=category)
        data = s.ApprovalPolicyUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        policy = services.update_policy(request._request, policy, dict(data.validated_data))
        return Response(s.ApprovalPolicySerializer(policy).data)


@extend_schema(
    tags=["approvals"],
    parameters=[
        OpenApiParameter("status", str, enum=[c for c, _ in ApprovalRequest.Status.choices]),
        OpenApiParameter("actionable", bool, description="Only requests I can decide."),
    ],
)
class RequestListView(generics.ListAPIView):
    serializer_class = s.ApprovalRequestSerializer

    def get_queryset(self):
        params = self.request.query_params
        user = self.request.user
        qs = (
            services.actionable_for(user)
            if params.get("actionable") in ("1", "true")
            else services.visible_to(user)
        )
        if params.get("status") in ApprovalRequest.Status.values:
            qs = qs.filter(status=params["status"])
        return qs.select_related("requested_by", "reviewed_by").order_by("-requested_at")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "user": self.request.user}


@extend_schema(
    tags=["approvals"], request=s.DecisionSerializer, responses=s.ApprovalRequestSerializer
)
class DecisionView(APIView):
    approve = True

    def post(self, request: Request, pk: int) -> Response:
        data = s.DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        approval = services.decide(
            request._request, pk, approve=self.approve, reason=data.validated_data["reason"]
        )
        return Response(s.ApprovalRequestSerializer(approval, context={"user": request.user}).data)


@extend_schema(tags=["approvals"], request=None, responses=s.ApprovalRequestSerializer)
class CancelView(APIView):
    def post(self, request: Request, pk: int) -> Response:
        approval = services.cancel(request._request, pk)
        return Response(s.ApprovalRequestSerializer(approval, context={"user": request.user}).data)
