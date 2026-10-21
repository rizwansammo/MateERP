from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views as v

router = SimpleRouter()
router.register("ownership/classes", v.ClassViewSet, basename="ownership-classes")
router.register("ownership/proposals", v.ProposalViewSet, basename="ownership-proposals")
urlpatterns = router.urls + [
    path("ownership/register/", v.RegisterView.as_view()),
    path("ownership/capital/", v.CapitalView.as_view()),
]
