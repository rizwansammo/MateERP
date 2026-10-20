from datetime import date

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import exceptions, serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import IsActiveUser, requires, requires_any
from apps.approvals.api.serializers import ApprovalRequestSerializer
from apps.approvals.services import approval_required
from apps.branding import services
from apps.branding.models import BrandingVersion
from apps.company.reference import CURRENCIES
from apps.company.services import get_business_settings, get_company, render_number
from apps.files.api.serializers import file_url

from . import serializers as s

READERS = ("branding.manage", "company.view")


def _company_preview() -> dict | None:
    company = get_company()
    if company is None:
        return None
    return {
        "display_name": company.display_name,
        "legal_name": company.legal_name,
        "address_lines": company.address_lines,
        "email": company.email,
        "phone": company.phone,
        "website": company.website,
        "tax_id": company.tax_id,
        "registration_number": company.registration_number,
        "base_currency": company.base_currency,
        "logo_url": file_url(company.logo),
    }


def _overview(request: Request) -> dict:
    user = request.user
    draft = services.get_draft()
    version = services.current_version()
    pending = services.pending_publication()
    business = get_business_settings()
    numbering = business.numbering
    company = get_company()
    base = company.base_currency if company else "BDT"
    today = date.today()
    return {
        "current": (
            s.VersionDetailSerializer(version, context={"user": user}).data if version else None
        ),
        "draft": s.DraftSerializer(draft, context={"user": user}).data,
        "has_unpublished_changes": services.has_unpublished_changes(draft, version),
        "versions": s.VersionSummarySerializer(
            BrandingVersion.objects.select_related("published_by", "restored_from"), many=True
        ).data,
        "pending_request": (
            ApprovalRequestSerializer(pending, context={"user": user}).data if pending else None
        ),
        "approval_required": approval_required(services.PUBLISH_ACTION),
        "company": _company_preview(),
        # How amounts are shown on documents (Settings → Currency / Tax).
        "display": {
            "currency": base,
            "symbol": CURRENCIES[base].symbol if base in CURRENCIES else base,
            "currency_display": business.currency_display,
            "number_grouping": business.number_grouping,
            "tax_label": business.tax_label,
        },
        "numbering": {
            "invoice": numbering["invoice"],
            "receipt": numbering["receipt"],
            "next_invoice": render_number(numbering["invoice"], today, 1),
            "next_receipt": render_number(numbering["receipt"], today, 1),
        },
    }


OVERVIEW_SCHEMA = inline_serializer(
    "BrandingOverview",
    {
        "current": s.VersionDetailSerializer(allow_null=True),
        "draft": s.DraftSerializer(),
        "has_unpublished_changes": serializers.BooleanField(),
        "versions": s.VersionSummarySerializer(many=True),
        "pending_request": ApprovalRequestSerializer(allow_null=True),
        "approval_required": serializers.BooleanField(),
        "company": serializers.DictField(allow_null=True),
        "display": serializers.DictField(),
        "numbering": serializers.DictField(),
    },
)


@extend_schema(tags=["branding"])
class BrandingOverviewView(APIView):
    permission_classes = [IsActiveUser, requires_any(*READERS)]

    @extend_schema(responses=OVERVIEW_SCHEMA)
    def get(self, request: Request) -> Response:
        return Response(_overview(request))


@extend_schema(tags=["branding"])
class DraftView(APIView):
    permission_classes = [IsActiveUser, requires("branding.manage")]

    @extend_schema(request=s.DraftUpdateSerializer, responses=OVERVIEW_SCHEMA)
    def put(self, request: Request) -> Response:
        data = s.DraftUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.save_draft(request._request, data.validated_data["config"])
        return Response(_overview(request))


@extend_schema(tags=["branding"])
class DraftDiscardView(APIView):
    permission_classes = [IsActiveUser, requires("branding.manage")]

    @extend_schema(request=None, responses=OVERVIEW_SCHEMA)
    def post(self, request: Request) -> Response:
        services.discard_draft(request._request)
        return Response(_overview(request))


@extend_schema(tags=["branding"])
class DraftAssetView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsActiveUser, requires("branding.manage")]

    @extend_schema(
        request={
            "multipart/form-data": inline_serializer(
                "BrandingAssetUpload", {"file": serializers.ImageField()}
            )
        },
        responses=OVERVIEW_SCHEMA,
    )
    def post(self, request: Request, kind: str) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            raise exceptions.ValidationError({"file": ["Choose an image to upload."]})
        services.set_draft_asset(request._request, kind, upload)
        return Response(_overview(request))

    @extend_schema(responses=OVERVIEW_SCHEMA)
    def delete(self, request: Request, kind: str) -> Response:
        services.remove_draft_asset(request._request, kind)
        return Response(_overview(request))


def _publish_response(request: Request, outcome: str, obj) -> Response:
    if outcome == "published":
        body = {
            "status": "published",
            "version": s.VersionDetailSerializer(obj, context={"user": request.user}).data,
        }
        return Response(body, status=status.HTTP_201_CREATED)
    body = {
        "status": "pending_approval",
        "request": ApprovalRequestSerializer(obj, context={"user": request.user}).data,
    }
    return Response(body, status=status.HTTP_202_ACCEPTED)


PUBLISH_SCHEMA = {
    201: inline_serializer(
        "Published", {"status": serializers.CharField(), "version": s.VersionDetailSerializer()}
    ),
    202: inline_serializer(
        "PendingApproval",
        {"status": serializers.CharField(), "request": ApprovalRequestSerializer()},
    ),
}


@extend_schema(tags=["branding"])
class PublishView(APIView):
    permission_classes = [IsActiveUser, requires("branding.manage")]

    @extend_schema(request=s.PublishSerializer, responses=PUBLISH_SCHEMA)
    def post(self, request: Request) -> Response:
        data = s.PublishSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        outcome, obj = services.publish(request._request, **data.validated_data)
        return _publish_response(request, outcome, obj)


@extend_schema(tags=["branding"])
class VersionDetailView(APIView):
    permission_classes = [IsActiveUser, requires_any(*READERS)]

    @extend_schema(responses=s.VersionDetailSerializer)
    def get(self, request: Request, number: int) -> Response:
        version = get_object_or_404(BrandingVersion, number=number)
        return Response(s.VersionDetailSerializer(version, context={"user": request.user}).data)


@extend_schema(tags=["branding"])
class VersionRestoreView(APIView):
    permission_classes = [IsActiveUser, requires("branding.manage")]

    @extend_schema(request=None, responses=PUBLISH_SCHEMA)
    def post(self, request: Request, number: int) -> Response:
        version = get_object_or_404(BrandingVersion, number=number)
        outcome, obj = services.restore(request._request, version)
        return _publish_response(request, outcome, obj)
