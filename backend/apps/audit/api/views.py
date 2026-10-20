from datetime import datetime, time

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import IsActiveUser, requires
from apps.audit.models import AuditEvent

from .serializers import AuditEventSerializer


def _parse_date(value: str | None, end: bool):
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise serializers.ValidationError({"date": ["Use YYYY-MM-DD dates."]}) from exc
    return timezone.make_aware(datetime.combine(day, time.max if end else time.min))


@extend_schema(
    tags=["audit"],
    parameters=[
        OpenApiParameter("date_from", str, description="YYYY-MM-DD (inclusive)"),
        OpenApiParameter("date_to", str, description="YYYY-MM-DD (inclusive)"),
        OpenApiParameter("actor", int),
        OpenApiParameter("category", str),
        OpenApiParameter("action", str),
        OpenApiParameter("outcome", str, enum=[c for c, _ in AuditEvent.Outcome.choices]),
        OpenApiParameter("q", str, description="Search target, actor or action"),
    ],
)
class AuditEventListView(generics.ListAPIView):
    """Read-only, server-paginated audit history (there is no write API)."""

    permission_classes = [IsActiveUser, requires("audit.view")]
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        params = self.request.query_params
        qs = AuditEvent.objects.all()
        if start := _parse_date(params.get("date_from"), end=False):
            qs = qs.filter(occurred_at__gte=start)
        if stop := _parse_date(params.get("date_to"), end=True):
            qs = qs.filter(occurred_at__lte=stop)
        if (actor := params.get("actor")) and actor.isdigit():
            qs = qs.filter(actor_id=int(actor))
        if category := params.get("category"):
            qs = qs.filter(category=category)
        if action := params.get("action"):
            qs = qs.filter(action=action)
        if params.get("outcome") in AuditEvent.Outcome.values:
            qs = qs.filter(outcome=params["outcome"])
        # Activity of one record, e.g. target_type=billing.invoice&target_id=12 (indexed).
        if target_type := params.get("target_type"):
            qs = qs.filter(target_type=target_type[:64])
        if target_id := params.get("target_id"):
            qs = qs.filter(target_id=target_id[:64])
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(target_label__icontains=q)
                | Q(actor_label__icontains=q)
                | Q(action__icontains=q)
                | Q(request_id=q)
            )
        return qs.order_by("-occurred_at")


@extend_schema(tags=["audit"])
class AuditFacetsView(APIView):
    """Distinct filter values for the audit log UI."""

    permission_classes = [IsActiveUser, requires("audit.view")]

    @extend_schema(
        responses=inline_serializer(
            "AuditFacets",
            {
                "categories": serializers.ListField(child=serializers.CharField()),
                "actions": serializers.ListField(child=serializers.CharField()),
            },
        )
    )
    def get(self, request: Request) -> Response:
        return Response(
            {
                "categories": sorted(
                    AuditEvent.objects.order_by("category")
                    .values_list("category", flat=True)
                    .distinct()
                ),
                "actions": sorted(
                    AuditEvent.objects.order_by("action")
                    .values_list("action", flat=True)
                    .distinct()
                ),
            }
        )
