"""Test-only routes that exercise the API error conventions."""

from django.urls import include, path
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class ProtectedView(APIView):
    def get(self, request):
        return Response({"ok": True})


class _AmountSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class ValidationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = _AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class BoomView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        raise RuntimeError("internal detail that must not leak")


_patterns = [
    path("protected/", ProtectedView.as_view()),
    path("validate/", ValidationView.as_view()),
    path("boom/", BoomView.as_view()),
]

urlpatterns = [
    path("api/v1/", include((_patterns, "v1"), namespace="v1")),
]
