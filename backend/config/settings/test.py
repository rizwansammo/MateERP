"""Automated test settings. Tests run against a real PostgreSQL database."""

import tempfile

from .base import *  # noqa: F403
from .base import LOGGING

MATEERP_ENVIRONMENT = "test"
DEBUG = False

SECRET_KEY = "test-only-secret-key-not-used-anywhere-else-0123456789"
ALLOWED_HOSTS = ["testserver", "localhost"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Uploaded files go to a throwaway directory, never the real storage volume.
PRIVATE_STORAGE_ROOT = tempfile.mkdtemp(prefix="mateerp-test-storage-")
MATEERP_TRUSTED_PROXIES = ["10.99.0.0/16"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:3100"]

LOGGING["root"]["level"] = "WARNING"
LOGGING["loggers"]["mateerp"]["level"] = "WARNING"
