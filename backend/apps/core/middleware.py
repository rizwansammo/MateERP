"""Request correlation and request logging."""

import logging
import re
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from django.http import HttpRequest, HttpResponse

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,128}")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

logger = logging.getLogger("mateerp.request")


def get_request_id() -> str | None:
    """Return the correlation id of the request being handled, if any."""
    return _request_id.get()


class RequestIdMiddleware:
    """Assign every request a correlation id and log one line per request.

    A well-formed incoming ``X-Request-ID`` is reused so ids can be traced
    across the frontend proxy and the backend; anything else is replaced.
    Only the path is logged, never the query string, which may contain
    personal or financial data.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        token = _request_id.set(request_id)
        request.request_id = request_id  # type: ignore[attr-defined]
        started = time.perf_counter()
        try:
            response = self.get_response(request)
            # Financial API responses should not be cached by browsers or
            # intermediary proxies unless a view makes a deliberate, safe
            # exception (e.g. versioned public company artwork).
            if request.path.startswith("/api/"):
                response.setdefault("Cache-Control", "private, no-store")
            response[REQUEST_ID_HEADER] = request_id
            logger.info(
                "%s %s %s",
                request.method,
                request.path,
                response.status_code,
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            return response
        finally:
            _request_id.reset(token)
