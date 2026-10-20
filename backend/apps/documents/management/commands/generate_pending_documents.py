"""Render official PDFs that are pending or failed (safe to repeat)."""

from django.core.management.base import BaseCommand

from apps.documents.services import generate_pending


class Command(BaseCommand):
    help = "Retry official PDF generation for issued invoices, receipts and credit notes."

    def handle(self, *args, **options):
        for kind, counts in generate_pending().items():
            self.stdout.write(f"{kind}: {counts['ready']} ready, {counts['failed']} still failing")
