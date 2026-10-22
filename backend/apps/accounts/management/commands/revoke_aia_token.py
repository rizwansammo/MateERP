"""Revoke one AIA token by public prefix (never accept a full secret in CLI arguments)."""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.integration import revoke_token


class Command(BaseCommand):
    help = "Revoke an AIA bearer token by its non-secret 16-character prefix."

    def add_arguments(self, parser):
        parser.add_argument("prefix")

    def handle(self, *args, **options):
        try:
            revoked = revoke_token(options["prefix"])
        except Exception as exc:
            raise CommandError("Could not find/revoke token for given prefix.") from exc
        self.stdout.write("Revoked" if revoked else "Already revoked")
