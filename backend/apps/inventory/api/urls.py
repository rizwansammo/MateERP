from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    AdjustmentView,
    LocationViewSet,
    MovementViewSet,
    OverviewView,
    PositionView,
    StockCountViewSet,
    TransferView,
    ValuationView,
)

router = SimpleRouter()
router.register("locations", LocationViewSet)
router.register("movements", MovementViewSet)
router.register("counts", StockCountViewSet)
urlpatterns = [
    path("inventory/summary/", OverviewView.as_view()),
    path("inventory/adjustments/", AdjustmentView.as_view()),
    path("inventory/transfers/", TransferView.as_view()),
    path("inventory/valuation/", ValuationView.as_view()),
    path("inventory/position/", PositionView.as_view()),
    path("inventory/", include(router.urls)),
]
