from django.urls import path

from . import views

urlpatterns = [
    path("branding/", views.BrandingOverviewView.as_view(), name="branding"),
    path("branding/draft/", views.DraftView.as_view(), name="branding-draft"),
    path("branding/draft/discard/", views.DraftDiscardView.as_view(), name="branding-discard"),
    path(
        "branding/draft/assets/<str:kind>/", views.DraftAssetView.as_view(), name="branding-asset"
    ),
    path("branding/publish/", views.PublishView.as_view(), name="branding-publish"),
    path(
        "branding/versions/<int:number>/",
        views.VersionDetailView.as_view(),
        name="branding-version",
    ),
    path(
        "branding/versions/<int:number>/restore/",
        views.VersionRestoreView.as_view(),
        name="branding-restore",
    ),
]
