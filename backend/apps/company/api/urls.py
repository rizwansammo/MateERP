from django.urls import path

from . import views

urlpatterns = [
    path("company/", views.CompanyView.as_view(), name="company"),
    path("company/summary/", views.CompanySummaryView.as_view(), name="company-summary"),
    path("company/logo/", views.CompanyLogoView.as_view(), name="company-logo"),
    path("settings/business/", views.BusinessSettingsView.as_view(), name="business-settings"),
    path(
        "settings/numbering/preview/",
        views.NumberingPreviewView.as_view(),
        name="numbering-preview",
    ),
    path("modules/", views.ModuleListView.as_view(), name="modules"),
    path("modules/<str:key>/", views.ModuleDetailView.as_view(), name="module-detail"),
    path("reference/currencies/", views.CurrencyListView.as_view(), name="currencies"),
    path("reference/timezones/", views.TimeZoneListView.as_view(), name="timezones"),
]
