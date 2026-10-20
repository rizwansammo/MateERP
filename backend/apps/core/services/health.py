"""Service health checks. Reports status only — never configuration."""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

from django.conf import settings
from django.db import DatabaseError, connection
from django.utils import timezone

logger = logging.getLogger("mateerp.health")

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CheckResult:
    status: str
    latency_ms: float | None = None


@dataclass(frozen=True)
class HealthReport:
    status: str
    service: str
    version: str
    environment: str
    time: datetime
    checks: dict[str, CheckResult] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return self.status == STATUS_OK


def check_database() -> CheckResult:
    started = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        # Details go to the log only; the response must not leak them.
        logger.warning("Database health check failed", exc_info=True)
        return CheckResult(status=STATUS_UNAVAILABLE)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return CheckResult(status=STATUS_OK, latency_ms=latency_ms)


def get_health_report() -> HealthReport:
    checks = {"database": check_database()}
    healthy = all(c.status == STATUS_OK for c in checks.values())
    overall = STATUS_OK if healthy else STATUS_UNAVAILABLE
    return HealthReport(
        status=overall,
        service="mateerp-backend",
        version=settings.MATEERP_VERSION,
        environment=settings.MATEERP_ENVIRONMENT,
        time=timezone.now(),
        checks=checks,
    )
