"""Report storage inconsistencies. Never deletes anything."""

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.files.models import StoredFile


class Command(BaseCommand):
    help = "List stored files without database records and records whose file is missing."

    def handle(self, *args, **options):
        root = settings.PRIVATE_STORAGE_ROOT
        known = set(StoredFile.objects.values_list("storage_name", flat=True))
        on_disk = set()
        for folder, _dirs, files in os.walk(root):
            for name in files:
                on_disk.add(os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/"))
        orphans = sorted(on_disk - known)
        missing = sorted(known - on_disk)
        for name in orphans:
            self.stdout.write(f"orphan file: {name}")
        for name in missing:
            self.stdout.write(f"missing file: {name}")
        self.stdout.write(
            f"{len(orphans)} orphan files, {len(missing)} missing files (report only)."
        )
