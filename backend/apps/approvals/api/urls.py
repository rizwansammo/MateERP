from django.urls import path

from . import views

urlpatterns = [
    path("approvals/policies/", views.PolicyListView.as_view(), name="approval-policies"),
    path(
        "approvals/policies/<str:category>/",
        views.PolicyDetailView.as_view(),
        name="approval-policy",
    ),
    path("approvals/requests/", views.RequestListView.as_view(), name="approval-requests"),
    path(
        "approvals/requests/<int:pk>/approve/",
        views.DecisionView.as_view(approve=True),
        name="approval-approve",
    ),
    path(
        "approvals/requests/<int:pk>/reject/",
        views.DecisionView.as_view(approve=False),
        name="approval-reject",
    ),
    path("approvals/requests/<int:pk>/cancel/", views.CancelView.as_view(), name="approval-cancel"),
]
