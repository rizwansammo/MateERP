"""Provision an expiring AIA bearer token; write stdout directly to an owner-only file."""

import sys

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.integration import DEFAULT_SCOPES, issue_token


class Command(BaseCommand):
    help = "Issue an AIA integration token. SECRET OUTPUT: redirect stdout to a 0600 file."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="MateERP AIA access")
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--scopes", default=",".join(sorted(DEFAULT_SCOPES)))

    def handle(self, *args, **options):
        if sys.stdout.isatty():
            raise CommandError(
                "Refusing to print credentials to a terminal. Redirect output to a 0600 file."
            )
        try:
            token = issue_token(
                name=options["name"],
                days=options["days"],
                scopes=set(options["scopes"].split(",")),
            )
        except (ValueError, LookupError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(token)
