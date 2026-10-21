from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import procurement as p
from . import views as v

router = SimpleRouter()
router.register("vendors", v.VendorViewSet)
router.register("bills", v.BillViewSet)
router.register("expenses", v.ExpenseViewSet)
router.register("payments", v.VendorPaymentViewSet)
router.register("recurring", v.ExpenseScheduleViewSet)
router.register("orders", p.OrderViewSet)
router.register("receipts", p.ReceiptViewSet)
urlpatterns = [
    path("purchasing/overview/", v.PurchasingOverviewView.as_view()),
    path("purchasing/reconciliation/", v.PayablesReconciliationView.as_view()),
    path("purchasing/history/", v.PurchaseHistoryView.as_view()),
    path("purchasing/vendors/<int:pk>/statement/", v.VendorStatementView.as_view()),
    path("purchasing/", include(router.urls)),
]
