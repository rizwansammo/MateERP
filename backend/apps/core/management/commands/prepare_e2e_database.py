import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql


class Command(BaseCommand):
    help = "Create a new, empty browser-test database. Never resets or drops an existing database."

    def add_arguments(self, parser):
        parser.add_argument("name")

    def handle(self, *args, **options):
        name = options["name"]
        if settings.MATEERP_ENVIRONMENT != "development" or not re.fullmatch(
            r"mateerp_e2e_[a-z0-9_]{8,40}", name
        ):
            raise CommandError("Only new mateerp_e2e_* databases may be created from development.")
        with connection.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", [name])
            if cur.fetchone():
                raise CommandError("This database already exists. Generate a new run identifier.")
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        self.stdout.write(f"Created isolated browser-test database {name}.")
