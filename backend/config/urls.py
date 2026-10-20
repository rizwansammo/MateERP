from django.urls import include, path, re_path

from apps.core.api.views import api_not_found

urlpatterns = [
    path("api/v1/", include(("config.api_v1", "v1"), namespace="v1")),
    # Anything else under /api/ gets a JSON 404 in the standard error format.
    re_path(r"^api(?:/.*)?$", api_not_found),
]

handler500 = "apps.core.api.views.server_error"
