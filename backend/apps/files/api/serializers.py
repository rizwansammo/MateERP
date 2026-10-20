from django.urls import reverse
from rest_framework import serializers

from apps.files.models import StoredFile


def file_url(stored: StoredFile | None) -> str | None:
    if stored is None:
        return None
    return reverse("v1:file-content", kwargs={"file_id": stored.pk})


class StoredFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = StoredFile
        fields = [
            "id",
            "purpose",
            "original_name",
            "content_type",
            "size",
            "width",
            "height",
            "created_at",
            "url",
        ]
        read_only_fields = fields

    def get_url(self, obj: StoredFile) -> str | None:
        return file_url(obj)
