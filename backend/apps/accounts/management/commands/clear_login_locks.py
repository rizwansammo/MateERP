from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services import throttle
from apps.audit.services import record


class Command(BaseCommand):
    help = "Clear recorded sign-in failures (lifts throttling early)."

    def add_arguments(self, parser):
        parser.add_argument("--identifier", help="Username or email to clear.")
        parser.add_argument("--ip", help="Client IP address to clear.")
        parser.add_argument("--all", action="store_true", help="Clear every recorded failure.")

    def handle(self, *args, **options):
        identifier, ip = options["identifier"], options["ip"]
        if not (identifier or ip or options["all"]):
            raise CommandError("Pass --identifier, --ip or --all.")
        removed = throttle.clear(identifier=identifier, ip=ip)
        record(
            "auth.locks_cleared",
            target_type="login",
            target_label="sign-in throttling",
            after={"identifier_given": bool(identifier), "ip": ip, "removed": removed},
            reason="manage.py clear_login_locks",
        )
        self.stdout.write(self.style.SUCCESS(f"Cleared {removed} recorded failure(s)."))
