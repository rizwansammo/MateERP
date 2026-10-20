from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views as v
from .references import FilingReferencesView

router = SimpleRouter()
router.register("documents", v.DocumentViewSet, basename="document")
urlpatterns = [
    path("documents/references/", FilingReferencesView.as_view()),
    path("documents/client-tree/", v.ClientTreeView.as_view()),
    path("documents/vendor-tree/", v.VendorTreeView.as_view()),
    path("", include(router.urls)),
]
