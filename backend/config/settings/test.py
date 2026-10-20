"""Automated test settings. Tests run against a real PostgreSQL database."""

from .base import *  # noqa: F403
from .base import LOGGING

MATEERP_ENVIRONMENT = "test"
DEBUG = False

SECRET_KEY = "test-only-secret-key-not-used-anywhere-else-0123456789"
ALLOWED_HOSTS = ["testserver", "localhost"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOGGING["root"]["level"] = "WARNING"
LOGGING["loggers"]["mateerp"]["level"] = "WARNING"
