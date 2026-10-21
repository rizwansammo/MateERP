from django.http import FileResponse, Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.audit.services import record
from apps.files.access import can_read
from apps.files.models import FilePurpose, StoredFile
from apps.files.services import private_storage


class FileContentView(APIView):
    """Stream a private file after purpose-specific, object-level checks."""

    @extend_schema(responses={(200, "image/*"): OpenApiTypes.BINARY}, tags=["files"])
    def get(self, request: Request, file_id) -> FileResponse:
        stored = StoredFile.objects.filter(pk=file_id).first()
        # Unauthorised and missing files look identical (no existence leak).
        if stored is None or not can_read(request.user, stored):
            raise Http404
        storage = private_storage()
        if not storage.exists(stored.storage_name):
            raise Http404
        if stored.purpose == FilePurpose.BANK_PROOF:
            # Restricted banking evidence: every successful view is attributable.
            record("documents.bank_proof_viewed", request=request, target=stored)
        response = FileResponse(
            storage.open(stored.storage_name, "rb"), content_type=stored.content_type
        )
        response["Content-Length"] = str(stored.size)
        disposition = "attachment" if request.query_params.get("download") == "1" else "inline"
        response["Content-Disposition"] = (
            f'{disposition}; filename="{stored.original_name or stored.pk}"'
        )
        response["X-Content-Type-Options"] = "nosniff"
        sensitive = stored.purpose in (
            FilePurpose.HISTORICAL_EVIDENCE,
            FilePurpose.PROCUREMENT_EVIDENCE,
            FilePurpose.ASSET_EVIDENCE,
            FilePurpose.BANK_PROOF,
            FilePurpose.CLIENT_DOCUMENT,
            FilePurpose.VENDOR_DOCUMENT,
        )
        response["Cache-Control"] = "private, no-store" if sensitive else "private, max-age=300"
        response["ETag"] = f'"{stored.sha256}"'
        # PDFs open in the browser's built-in viewer, which a CSP sandbox would block;
        # uploaded PDFs are checked for scripts/actions before storage instead.
        response["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'self'"
            if stored.content_type == "application/pdf"
            else "default-src 'none'; sandbox"
        )
        response["Cross-Origin-Resource-Policy"] = "same-origin"
        return response
