from django.urls import path

from .views import AuditEventListView, AuditFacetsView

urlpatterns = [
    path("audit/events/", AuditEventListView.as_view(), name="audit-events"),
    path("audit/facets/", AuditFacetsView.as_view(), name="audit-facets"),
]
