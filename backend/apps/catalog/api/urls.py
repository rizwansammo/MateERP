from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import CategoryViewSet, ItemViewSet, UnitViewSet

router = SimpleRouter()
router.register("items", ItemViewSet)
router.register("categories", CategoryViewSet)
router.register("units", UnitViewSet)
urlpatterns = [path("catalog/", include(router.urls))]
