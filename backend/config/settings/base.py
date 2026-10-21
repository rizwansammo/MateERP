"""Settings shared by every environment.

All environment-specific values come from environment variables. Environment
modules (dev, test, prod) import from here and only override what differs.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# Native (non-Docker) runs read the repository-level .env; containers get
# their variables from Compose.
_ENV_FILE = BASE_DIR.parent / ".env"
if _ENV_FILE.is_file():
    environ.Env.read_env(_ENV_FILE)

MATEERP_VERSION = "0.5.0"
MATEERP_ENVIRONMENT = "base"

SECRET_KEY = env("DJANGO_SECRET_KEY", default="")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.audit",
    "apps.files",
    "apps.accounts",
    "apps.company",
    "apps.approvals",
    "apps.branding",
    "apps.accounting",
    "apps.banking",
    "apps.sales",
    "apps.billing",
    "apps.purchasing",
    "apps.documents",
    "apps.founders",
    "apps.ownership",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

# --- Database --------------------------------------------------------------
# Transactions are managed explicitly by domain services (see
# docs/architecture.md), not wrapped implicitly around every request.
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication ----------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.UsernameOrEmailBackend"]

# Server-side sessions in PostgreSQL. A session without "remember me" ends
# with the browser and after 12 idle hours; "remember me" extends the idle
# limit to 14 days. Every request renews the expiry (sliding window).
SESSION_COOKIE_NAME = "mateerp_session"
SESSION_COOKIE_AGE = 12 * 60 * 60
SESSION_REMEMBER_AGE = 14 * 24 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True

# The CSRF cookie must be readable by the frontend, which echoes it in the
# X-CSRFToken header (Django's standard double-submit check).
CSRF_COOKIE_NAME = "mateerp_csrftoken"
CSRF_COOKIE_HTTPONLY = False
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Proxies allowed to report the client address via X-Forwarded-For (CIDRs).
# Empty means REMOTE_ADDR is always used.
MATEERP_TRUSTED_PROXIES = env.list("MATEERP_TRUSTED_PROXIES", default=[])

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalisation ----------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="Asia/Dhaka")
USE_I18N = True
USE_TZ = True

# --- Static files ------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Private file storage ----------------------------------------------------
# Never exposed through a URL; files are streamed by authorised API views.
PRIVATE_STORAGE_ROOT = env("PRIVATE_STORAGE_ROOT", default=str(BASE_DIR / "storage"))
FILE_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024 * 1024

# --- Security baseline (tightened further in prod) --------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"

# --- Django REST Framework ---------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ("v1",),
    # Session auth that enforces CSRF on every unsafe request, including
    # anonymous ones such as login.
    "DEFAULT_AUTHENTICATION_CLASSES": ("apps.accounts.authentication.SessionAuthentication",),
    # Secure by default: every endpoint requires an active user who is not
    # pending a forced password change, unless it explicitly opts out.
    "DEFAULT_PERMISSION_CLASSES": ("apps.accounts.authorization.IsActiveUser",),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Monetary values are serialised as strings to avoid float conversion.
    "COERCE_DECIMAL_TO_STRING": True,
}

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=False)

SPECTACULAR_SETTINGS = {
    "TITLE": "MateERP API",
    "DESCRIPTION": "MateERP enterprise resource planning API.",
    "VERSION": MATEERP_VERSION,
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "ENUM_NAME_OVERRIDES": {
        "FinancialPartyKindEnum": [("individual", "Individual"), ("organization", "Organization")],
        "FounderTransactionKindEnum": [
            (x, x.replace("_", " ").title())
            for x in (
                "receipt",
                "expense",
                "vendor_payment",
                "reimbursement",
                "loan_repayment",
                "reclassify",
                "reassign",
            )
        ],
        "OwnershipEventKindEnum": [
            (x, x.title()) for x in ("provisional", "transfer", "issuance", "opening")
        ],
        "HealthStatusEnum": ["ok", "unavailable"],
        "ApprovalStatusEnum": "apps.approvals.models.ApprovalRequest.Status",
        "AuditOutcomeEnum": "apps.audit.models.AuditEvent.Outcome",
        "DiscountTypeEnum": [("percent", "Percent"), ("fixed", "Fixed")],
        "PaymentMethodEnum": "apps.purchasing.models.METHODS",
        "PdfStatusEnum": "apps.billing.models.PDF_STATUSES",
        "InvoiceStatusEnum": "apps.billing.models.Invoice.Status",
        "ClientPaymentStatusEnum": "apps.billing.models.CustomerPayment.Status",
        "ReceiptStatusEnum": "apps.billing.models.MoneyReceipt.Status",
        "CreditNoteStatusEnum": "apps.billing.models.CreditNote.Status",
        "RefundStatusEnum": "apps.billing.models.Refund.Status",
        "ScheduleStatusEnum": "apps.billing.models.RecurringInvoiceSchedule.Status",
        "ScheduleFrequencyEnum": "apps.billing.models.RecurringInvoiceSchedule.Frequency",
        "InvoiceRunStatusEnum": "apps.billing.models.RecurringInvoiceRun.Status",
        "ProjectStatusEnum": "apps.sales.models.Project.Status",
        "SalesOrderStatusEnum": "apps.sales.models.SalesOrder.Status",
        "PayableStatusEnum": "apps.purchasing.models.VendorBill.Status",
        "VendorPaymentStatusEnum": "apps.purchasing.models.VendorPayment.Status",
        "ScheduleTransitionEnum": ["active", "paused", "cancelled"],
    },
}

# --- Logging -----------------------------------------------------------------
LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")
LOG_FORMAT = env("DJANGO_LOG_FORMAT", default="json")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.logging.RequestIdFilter"}},
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
        "text": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": LOG_FORMAT,
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # Request lines are emitted by apps.core.middleware instead.
        "django.server": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "mateerp": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
