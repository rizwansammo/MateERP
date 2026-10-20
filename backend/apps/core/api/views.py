from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import defaults
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import error_payload
from apps.core.services.health import get_health_report

from .serializers import HealthSerializer


class HealthView(APIView):
    """Liveness and dependency status for monitoring and the frontend."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="health_retrieve",
        summary="Service health",
        responses={200: HealthSerializer, 503: HealthSerializer},
        tags=["system"],
    )
    def get(self, request: Request) -> Response:
        report = get_health_report()
        response = Response(
            HealthSerializer(report).data,
            status=200 if report.healthy else 503,
        )
        response["Cache-Control"] = "no-store"
        return response


def api_not_found(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        error_payload("not_found", "The requested API endpoint does not exist."), status=404
    )


def server_error(request: HttpRequest) -> HttpResponse:
    if request.path.startswith("/api/"):
        return JsonResponse(
            error_payload("server_error", "An unexpected error occurred."), status=500
        )
    return defaults.server_error(request)
