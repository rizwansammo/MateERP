from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    """Client and vendor document filing, official PDF generation and access policy."""

    name = "apps.documents"
    label = "documents"

    def ready(self) -> None:
        from . import services  # noqa: F401  (registers file purpose policies)
