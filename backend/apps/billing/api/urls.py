from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views as v

router = SimpleRouter()
router.register("invoices", v.InvoiceViewSet)
router.register("payments", v.PaymentViewSet)
router.register("receipts", v.ReceiptViewSet)
router.register("credit-notes", v.CreditNoteViewSet)
router.register("refunds", v.RefundViewSet)
router.register("recurring", v.ScheduleViewSet)
urlpatterns = [
    path("billing/overview/", v.OverviewView.as_view()),
    path("billing/reconciliation/", v.ReconciliationView.as_view()),
    path("billing/settings/", v.LedgerSettingsView.as_view()),
    path("billing/document-branding/", v.DocumentBrandingView.as_view()),
    path("billing/credit-applications/", v.CreditApplicationView.as_view()),
    path("billing/customer-balances/", v.CustomerBalancesView.as_view()),
    path("billing/customers/<int:pk>/account/", v.CustomerAccountView.as_view()),
    path("billing/projects/<int:pk>/financials/", v.ProjectFinancialsView.as_view()),
    path("billing/", include(router.urls)),
]
