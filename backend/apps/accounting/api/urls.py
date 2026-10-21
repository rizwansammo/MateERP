from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views as v
from .onboarding import HistoricalViewSet

router = SimpleRouter()
router.register("accounts", v.AccountViewSet)
router.register("journals", v.JournalViewSet)
router.register("fiscal-years", v.YearViewSet)
router.register("periods", v.PeriodViewSet)
router.register("exchange-rates", v.RateViewSet)
router.register("tax-codes", v.TaxViewSet)
router.register("historical-records", HistoricalViewSet)
urlpatterns = [
    path("accounting/config/", v.ConfigView.as_view()),
    path("accounting/tax-position/", v.TaxPositionView.as_view()),
    path("accounting/", include(router.urls)),
    path("accounting/ledger/<int:pk>/", v.LedgerView.as_view()),
    path("accounting/ledger/", v.ReportView.as_view()),
    path("accounting/reports/<str:which>/", v.ReportView.as_view()),
    path(
        "accounting/opening-balances/", v.JournalViewSet.as_view({"post": "create", "get": "list"})
    ),
]
