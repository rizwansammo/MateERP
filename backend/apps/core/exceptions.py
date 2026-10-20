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
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .middleware import get_request_id

logger = logging.getLogger("mateerp.api")


class BusinessRuleViolation(exceptions.APIException):
    """A request that is well-formed but conflicts with current state or a rule (409).

    Raise with a stable ``code`` so clients can react, e.g.
    ``BusinessRuleViolation("…", code="last_administrator")``.
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


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
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )
    elif isinstance(exc, IntegrityError):
        exc = BusinessRuleViolation(
            "The change violates a record integrity rule.", code="integrity_conflict"
        )
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
