"""Standard API error responses.

Every API error uses one envelope so the frontend can handle failures
uniformly::

    {"error": {"code": "not_found", "message": "...", "details": {...}, "request_id": "..."}}

``code`` is a stable machine-readable identifier; ``message`` is safe to show
to users; ``details`` carries field-level validation errors when relevant.
"""

import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .middleware import get_request_id

logger = logging.getLogger("mateerp.api")


def error_payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": get_request_id(),
        }
    }


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)

    if response is None:
        # Unhandled error. In development let Django render the traceback;
        # otherwise log it and return a generic envelope with no internals.
        if settings.DEBUG:
            return None
        logger.exception("Unhandled API error", exc_info=exc)
        return Response(
            error_payload("server_error", "An unexpected error occurred."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        response.data = error_payload(
            "validation_error", "The request contains invalid data.", response.data
        )
    elif isinstance(exc, exceptions.APIException):
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else exc.default_code
        detail = exc.detail
        message = str(detail) if isinstance(detail, str) else str(exc.default_detail)
        response.data = error_payload(str(code), message)
    return response
