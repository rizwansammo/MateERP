"""Local development settings."""

from .base import *  # noqa: F403
from .base import LOGGING, REST_FRAMEWORK, env

MATEERP_ENVIRONMENT = "development"
DEBUG = True

SECRET_KEY = env("DJANGO_SECRET_KEY", default="") or "django-insecure-local-development-only"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "backend"]

CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", default=["http://localhost:3100", "http://127.0.0.1:3100"]
)

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)

LOGGING["handlers"]["console"]["formatter"] = env("DJANGO_LOG_FORMAT", default="text")
