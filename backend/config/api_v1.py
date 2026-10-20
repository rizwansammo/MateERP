"""Version 1 API routes. Each domain module contributes its own urls module."""

from django.conf import settings
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("", include("apps.core.api.urls")),
    path("", include("apps.accounts.api.urls")),
    path("", include("apps.company.api.urls")),
    path("", include("apps.files.api.urls")),
    path("", include("apps.branding.api.urls")),
    path("", include("apps.approvals.api.urls")),
    path("", include("apps.audit.api.urls")),
    path("", include("apps.accounting.api.urls")),
    path("", include("apps.banking.api.urls")),
    path("", include("apps.sales.api.urls")),
    path("", include("apps.billing.api.urls")),
    path("", include("apps.purchasing.api.urls")),
    path("", include("apps.documents.api.urls")),
]

if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path("schema/", SpectacularAPIView.as_view(), name="schema"),
        path("docs/", SpectacularSwaggerView.as_view(url_name="v1:schema"), name="docs"),
    ]
