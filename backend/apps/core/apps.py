from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Cross-cutting platform concerns: errors, logging, health, shared utilities."""

    name = "apps.core"
    label = "core"
