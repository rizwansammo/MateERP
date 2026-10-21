from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views as v

router = SimpleRouter()
router.register("founders/consumptions", v.ConsumptionViewSet, basename="founders-consumptions")
router.register(
    "founders/company-coverage", v.CompanyCoverageViewSet, basename="founders-company-coverage"
)
for prefix, cls in [
    ("parties", v.PartyViewSet),
    ("loans", v.LoanViewSet),
    ("transactions", v.CorporateViewSet),
    ("policies", v.PolicyViewSet),
    ("sharing", v.SharingViewSet),
    ("settlements", v.PersonalViewSet),
    ("plans", v.PlanViewSet),
    ("reserves", v.ReserveViewSet),
    ("designations", v.DesignationViewSet),
    ("pledges", v.PledgeViewSet),
    ("resolutions", v.ResolutionViewSet),
    ("evidence", v.EvidenceViewSet),
]:
    router.register(f"founders/{prefix}", cls, basename=f"founders-{prefix}")
urlpatterns = router.urls + [
    path("founders/overview/", v.OverviewView.as_view()),
    path("founders/statements/", v.StatementView.as_view()),
    path("founders/obligations/", v.ObligationView.as_view()),
    path("founders/personal-balances/", v.PersonalBalanceView.as_view()),
]
