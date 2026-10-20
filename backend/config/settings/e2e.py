"""Browser acceptance environment: real sessions/CSRF, isolated database and files."""

from django.core.exceptions import ImproperlyConfigured

from .dev import *  # noqa: F403
from .dev import DATABASES

MATEERP_ENVIRONMENT = "e2e"
if not DATABASES["default"]["NAME"].startswith("mateerp_e2e_"):
    raise ImproperlyConfigured("Browser tests require an isolated mateerp_e2e_* database.")
