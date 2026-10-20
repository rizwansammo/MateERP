"""Run due recurring invoices and expenses (call daily from an OS scheduler).

MateERP has no background worker: schedule this command with Windows Task Scheduler
or cron, e.g. ``python manage.py run_recurring``. Occurrences are idempotent, so
overlapping or repeated runs never duplicate documents.
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.billing.services import recurring as billing
from apps.purchasing.services import recurring as purchasing


class Command(BaseCommand):
    help = "Create due recurring invoices and expenses up to --date (default today)."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="until", type=date.fromisoformat, default=None)
        parser.add_argument("--dry-run", action="store_true", help="List due occurrences only.")

    def handle(self, *args, until=None, dry_run=False, **options):
        until = until or timezone.localdate()
        if dry_run:
            for row in billing.preview(until):
                if row["dates"]:
                    dates = ", ".join(str(d) for d in row["dates"])
                    self.stdout.write(f"invoice schedule {row['schedule'].pk}: {dates}")
            from apps.purchasing.models import RecurringExpenseSchedule

            for schedule in RecurringExpenseSchedule.objects.filter(status="active"):
                dates = ", ".join(str(d) for d in purchasing.due_occurrences(schedule, until))
                if dates:
                    self.stdout.write(f"expense schedule {schedule.pk}: {dates}")
            return
        results = billing.run_due(until) + purchasing.run_due(until)
        for row in results:
            line = f"{row['schedule']} {row['date']} {row['status']} {row.get('message', '')}"
            self.stdout.write(line.rstrip())
        failed = sum(1 for row in results if row["status"] == "failed")
        self.stdout.write(
            self.style.SUCCESS(f"{len(results)} occurrences processed, {failed} failed.")
        )
