"""Create an initial MateERP administrator.

There are no default credentials. The password comes from an interactive
prompt, or from the MATEERP_ADMIN_PASSWORD environment variable for
non-interactive setup; it is never accepted as a command-line argument (which
would leak into shell history and process lists).
"""

import getpass
import os
import sys

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.api.serializers import USERNAME_PATTERN
from apps.accounts.catalog import ADMIN_ROLE_KEY
from apps.accounts.models import Role, User
from apps.audit.services import record


class Command(BaseCommand):
    help = "Create an administrator account (first-time setup)."

    def add_arguments(self, parser):
        parser.add_argument("--username")
        parser.add_argument("--email")
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")
        parser.add_argument(
            "--force-additional",
            action="store_true",
            help="Allow creating another administrator when one already exists.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Never prompt; read the password from MATEERP_ADMIN_PASSWORD.",
        )

    def _ask(self, label: str, value: str | None, no_input: bool) -> str:
        if value:
            return value.strip()
        if no_input:
            raise CommandError(f"--{label.lower()} is required with --no-input.")
        answer = input(f"{label}: ").strip()
        if not answer:
            raise CommandError(f"{label} is required.")
        return answer

    def _password(self, no_input: bool) -> str:
        env_password = os.environ.get("MATEERP_ADMIN_PASSWORD")
        if env_password:
            return env_password
        if no_input or not sys.stdin.isatty():
            raise CommandError(
                "No terminal for a password prompt. Set MATEERP_ADMIN_PASSWORD or run "
                "interactively (docker compose exec backend python manage.py create_admin)."
            )
        first = getpass.getpass("Password: ")
        if first != getpass.getpass("Password (again): "):
            raise CommandError("Passwords do not match.")
        return first

    def handle(self, *args, **options):
        if (
            User.objects.filter(is_active=True, role__is_admin=True).exists()
            and not options["force_additional"]
        ):
            raise CommandError(
                "An active administrator already exists. Sign in as that administrator to add "
                "users, or pass --force-additional for recovery."
            )
        admin_role = Role.objects.filter(key=ADMIN_ROLE_KEY, is_admin=True).first()
        if admin_role is None:
            raise CommandError("Administrator role missing; run migrations first.")

        no_input = options["no_input"]
        username = self._ask("Username", options["username"], no_input)
        email = self._ask("Email", options["email"], no_input)
        if not USERNAME_PATTERN.match(username):
            raise CommandError(
                "Username must be 3–150 letters, digits, dots, hyphens or underscores."
            )
        if User.objects.filter(username__iexact=username).exists():
            raise CommandError("That username is already taken.")
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("That email address is already in use.")

        user = User(
            username=username,
            email=email,
            first_name=options["first_name"],
            last_name=options["last_name"],
            role=admin_role,
            is_active=True,
        )
        password = self._password(no_input)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError("Password rejected: " + " ".join(exc.messages)) from exc

        with transaction.atomic():
            user.set_password(password)
            user.save()
            record(
                "user.admin_bootstrapped",
                target=user,
                after={"role": admin_role.name},
                reason="Created with manage.py create_admin",
            )
        self.stdout.write(self.style.SUCCESS(f"Administrator '{username}' created."))
