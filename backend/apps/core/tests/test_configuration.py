import os
import secrets
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection

BACKEND_DIR = Path(__file__).resolve().parents[3]
STRONG_KEY = secrets.token_urlsafe(50)


def test_settings_load_with_expected_foundations():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert settings.USE_TZ is True
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert settings.DATABASES["default"]["ATOMIC_REQUESTS"] is False
    assert settings.REST_FRAMEWORK["COERCE_DECIMAL_TO_STRING"] is True
    assert settings.DEBUG is False


@pytest.mark.django_db
def test_postgresql_connection_works():
    with connection.cursor() as cursor:
        cursor.execute("SELECT version()")
        (version,) = cursor.fetchone()
    assert version.startswith("PostgreSQL")


@pytest.mark.django_db
def test_no_model_changes_are_missing_migrations():
    out = StringIO()
    # Exits non-zero (SystemExit) if any model change lacks a migration.
    call_command("makemigrations", "--check", "--dry-run", stdout=out)


def _run_prod_check(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # Unset values are passed as empty strings so a local .env cannot fill them in.
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "API_DOCS"))}
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "DJANGO_SECRET_KEY": "",
            "DJANGO_ALLOWED_HOSTS": "",
            **extra_env,
        }
    )
    return subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_production_settings_pass_deploy_checks():
    result = _run_prod_check(
        {"DJANGO_SECRET_KEY": STRONG_KEY, "DJANGO_ALLOWED_HOSTS": "erp.example.com"}
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_production_settings_refuse_missing_secret_key():
    result = _run_prod_check({"DJANGO_ALLOWED_HOSTS": "erp.example.com"})
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_production_settings_refuse_missing_allowed_hosts():
    result = _run_prod_check({"DJANGO_SECRET_KEY": STRONG_KEY})
    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr
