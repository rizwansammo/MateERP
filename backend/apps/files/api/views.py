from django.http import FileResponse, Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.files.access import can_read
from apps.files.models import StoredFile
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
        response = FileResponse(
            storage.open(stored.storage_name, "rb"), content_type=stored.content_type
        )
        response["Content-Length"] = str(stored.size)
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, max-age=300"
        response["ETag"] = f'"{stored.sha256}"'
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["Cross-Origin-Resource-Policy"] = "same-origin"
        return response
