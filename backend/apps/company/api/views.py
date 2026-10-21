from dataclasses import asdict
from datetime import date
from zoneinfo import available_timezones

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import exceptions, serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import IsActiveUser, require, requires, requires_any
from apps.company import services
from apps.company.reference import CORE_MODULES, CURRENCIES, NUMBERING_KEYS, OPTIONAL_MODULES

from . import serializers as s

COMPANY_READERS = ("company.view", "company.edit", "branding.manage")


@extend_schema(tags=["company"])
class CompanyView(APIView):
    """The installation's single company profile."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsActiveUser(), requires_any(*COMPANY_READERS)()]
        return [IsActiveUser(), requires("company.edit")()]

    @extend_schema(responses=s.CompanyProfileSerializer)
    def get(self, request: Request) -> Response:
        company = services.get_company()
        if company is None:
            raise exceptions.NotFound(
                "The company profile has not been set up yet.", code="company_not_configured"
            )
        return Response(s.CompanyProfileSerializer(company).data)

    @extend_schema(request=s.CompanyProfileSerializer, responses={201: s.CompanyProfileSerializer})
    def post(self, request: Request) -> Response:
        data = s.CompanyProfileSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        company = services.create_company(request._request, data.validated_data)
        return Response(s.CompanyProfileSerializer(company).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.CompanyProfileSerializer, responses=s.CompanyProfileSerializer)
    def put(self, request: Request) -> Response:
        data = s.CompanyProfileSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        company = services.update_company(request._request, data.validated_data)
        return Response(s.CompanyProfileSerializer(company).data)

    @extend_schema(request=s.CompanyProfileSerializer, responses=s.CompanyProfileSerializer)
    def patch(self, request: Request) -> Response:
        data = s.CompanyProfileSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        company = services.update_company(request._request, data.validated_data)
        return Response(s.CompanyProfileSerializer(company).data)


@extend_schema(tags=["company"])
class CompanySummaryView(APIView):
    """Public-to-staff identity used by the application chrome (sidebar)."""

    @extend_schema(responses=s.CompanySummarySerializer)
    def get(self, request: Request) -> Response:
        return Response(s.CompanySummarySerializer.build(services.get_company()))


@extend_schema(tags=["company"])
class CompanyLogoView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsActiveUser, requires_any("company.edit", "branding.manage")]

    @extend_schema(
        request={
            "multipart/form-data": inline_serializer(
                "LogoUpload", {"file": serializers.ImageField()}
            )
        },
        responses=s.CompanyProfileSerializer,
    )
    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            raise exceptions.ValidationError({"file": ["Choose an image to upload."]})
        company = services.set_logo(request._request, upload)
        return Response(s.CompanyProfileSerializer(company).data)

    @extend_schema(responses=s.CompanyProfileSerializer)
    def delete(self, request: Request) -> Response:
        company = services.remove_logo(request._request)
        return Response(s.CompanyProfileSerializer(company).data)


@extend_schema(tags=["settings"])
class BusinessSettingsView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsActiveUser(), requires_any(*COMPANY_READERS)()]
        return [IsActiveUser(), requires("company.edit")()]

    @extend_schema(responses=s.BusinessSettingsSerializer)
    def get(self, request: Request) -> Response:
        return Response(s.BusinessSettingsSerializer(services.get_business_settings()).data)

    @extend_schema(request=s.BusinessSettingsSerializer, responses=s.BusinessSettingsSerializer)
    def patch(self, request: Request) -> Response:
        data = s.BusinessSettingsSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        obj = services.update_business_settings(request._request, dict(data.validated_data))
        return Response(s.BusinessSettingsSerializer(obj).data)


@extend_schema(tags=["settings"])
class NumberingPreviewView(APIView):
    """Preview what document numbers would look like (no sequence is reserved)."""

    @extend_schema(
        responses=inline_serializer(
            "NumberingPreview", {"examples": serializers.DictField(child=serializers.CharField())}
        )
    )
    def get(self, request: Request) -> Response:
        numbering = services.get_business_settings().numbering
        today = date.today()
        return Response(
            {
                "examples": {
                    k: services.render_number(numbering[k], today, 1) for k in NUMBERING_KEYS
                }
            }
        )


def _modules_payload() -> list[dict]:
    states = services.module_states()
    return [{**asdict(m), "enabled": states[m.key]} for m in OPTIONAL_MODULES]


@extend_schema(tags=["settings"])
class ModuleListView(APIView):
    @extend_schema(
        responses=inline_serializer(
            "Modules",
            {
                "optional": s.ModuleSerializer(many=True),
                "core": serializers.ListField(child=serializers.CharField()),
            },
        )
    )
    def get(self, request: Request) -> Response:
        return Response({"optional": _modules_payload(), "core": list(CORE_MODULES)})


@extend_schema(tags=["settings"])
class ModuleDetailView(APIView):
    @extend_schema(request=s.ModuleUpdateSerializer, responses=s.ModuleSerializer)
    def put(self, request: Request, key: str) -> Response:
        require(request.user, "company.edit")
        data = s.ModuleUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.set_module(request._request, key, data.validated_data["enabled"])
        return Response(next(m for m in _modules_payload() if m["key"] == key))


@extend_schema(tags=["reference"])
class CurrencyListView(APIView):
    @extend_schema(responses=s.CurrencySerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response([asdict(c) for c in CURRENCIES.values()])


@extend_schema(tags=["reference"])
class TimeZoneListView(APIView):
    @extend_schema(
        responses=inline_serializer("TimeZone", {"name": serializers.CharField()}, many=True)
    )
    def get(self, request: Request) -> Response:
        zones = sorted(z for z in available_timezones() if "/" in z and not z.startswith("Etc/"))
        return Response([{"name": z} for z in zones])
