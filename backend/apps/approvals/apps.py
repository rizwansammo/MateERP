from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _ensure_policies(**kwargs) -> None:
    from .services import ensure_policies

    ensure_policies()


class ApprovalsConfig(AppConfig):
    """Configurable approval policies and approval requests."""

    name = "apps.approvals"
    label = "approvals"

    def ready(self) -> None:
        post_migrate.connect(_ensure_policies, sender=self)
