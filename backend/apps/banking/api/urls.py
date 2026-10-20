from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views as v

router = SimpleRouter()
router.register("accounts", v.BankViewSet)
router.register("transactions", v.TransactionViewSet)
router.register("reconciliations", v.ReconciliationViewSet)
urlpatterns = [
    path("banking/overview/", v.OverviewView.as_view()),
    path("banking/", include(router.urls)),
    path("banking/statements/", v.ReconciliationViewSet.as_view({"post": "create", "get": "list"})),
]
