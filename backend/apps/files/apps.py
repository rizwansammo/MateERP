from django.apps import AppConfig


class FilesConfig(AppConfig):
    """Private file storage with validated uploads and object-level read access."""

    name = "apps.files"
    label = "files"
