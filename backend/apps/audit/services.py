"""Recording audit events. Never pass credentials; ``redact`` is a safety net."""

import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import models
from django.http import HttpRequest

from apps.core.middleware import get_request_id
from apps.core.net import client_ip

from .models import AuditEvent

_SENSITIVE_KEY = re.compile(
    r"pass(word)?|secret|token|session|csrf|api[_-]?key|private[_-]?key|credential|otp",
    re.IGNORECASE,
)
REDACTED = "[redacted]"
_MAX_STRING = 500


def redact(value: Any) -> Any:
    """Recursively replace values under sensitive-looking keys and trim long strings."""
    if isinstance(value, Mapping):
        return {
            str(k): (REDACTED if _SENSITIVE_KEY.search(str(k)) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str) and len(value) > _MAX_STRING:
        return value[:_MAX_STRING] + "…"
    if isinstance(value, Decimal):
        return format(value, "f")  # exact text, never a float
    if isinstance(value, date | UUID):
        return str(value)
    return value


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[dict, dict]:
    """Return only the keys whose values changed, as (before, after)."""
    keys = [k for k in after if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}


def record(
    action: str,
    *,
    request: HttpRequest | None = None,
    actor=None,
    target: models.Model | None = None,
    target_type: str = "",
    target_id: str = "",
    target_label: str = "",
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    outcome: str = AuditEvent.Outcome.SUCCESS,
    reason: str = "",
) -> AuditEvent:
    """Append one audit event.

    ``action`` is a dotted code such as ``user.created``; its first segment
    becomes the filterable category. The acting user defaults to the
    authenticated request user.
    """
    if actor is None and request is not None:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            actor = user
    if target is not None:
        target_type = target_type or target._meta.label_lower
        target_id = target_id or str(target.pk)
        target_label = target_label or str(target)[:200]

    return AuditEvent.objects.create(
        actor=actor,
        actor_label=actor.get_username() if actor is not None else "",
        action=action,
        category=action.split(".", 1)[0],
        target_type=target_type,
        target_id=target_id,
        target_label=target_label[:200],
        request_id=get_request_id() or "",
        ip_address=client_ip(request) if request is not None else None,
        before=redact(dict(before)) if before is not None else None,
        after=redact(dict(after)) if after is not None else None,
        outcome=outcome,
        reason=reason[:500],
    )
