from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    """User identity, authentication, roles and permissions."""

    name = "apps.accounts"
    label = "accounts"

    def ready(self) -> None:
        from . import schema  # noqa: F401  (registers the OpenAPI auth extension)
        from .defaults import ensure_permission_catalog

        post_migrate.connect(ensure_permission_catalog, sender=self)
