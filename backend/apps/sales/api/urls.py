from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views as v

router = SimpleRouter()
router.register("customers", v.CustomerViewSet)
router.register("projects", v.ProjectViewSet)
router.register("items", v.ItemViewSet)
router.register("orders", v.OrderViewSet)
urlpatterns = [
    path("sales/calculate/", v.CalculateView.as_view()),
    path("sales/", include(router.urls)),
]
