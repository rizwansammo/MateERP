from django.apps import AppConfig


class AuditConfig(AppConfig):
    """Append-only administrative and security audit trail."""

    name = "apps.audit"
    label = "audit"
