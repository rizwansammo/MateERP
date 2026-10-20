from django.apps import AppConfig


class BrandingConfig(AppConfig):
    """Invoice & receipt branding with immutable published versions."""

    name = "apps.branding"
    label = "branding"

    def ready(self) -> None:
        from apps.approvals.services import register_executor
        from apps.files.access import register_reference_resolver

        from .services import (
            PUBLISH_ACTION,
            branding_file_references,
            execute_approved_publication,
        )

        register_reference_resolver(branding_file_references)
        register_executor(PUBLISH_ACTION, execute_approved_publication)
