from django.urls import path

from . import views

urlpatterns = [
    path("auth/csrf/", views.CsrfView.as_view(), name="auth-csrf"),
    path("auth/session/", views.SessionView.as_view(), name="auth-session"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("auth/password/", views.PasswordChangeView.as_view(), name="auth-password"),
    path("users/", views.UserListCreateView.as_view(), name="users"),
    path("users/<int:pk>/", views.UserDetailView.as_view(), name="user-detail"),
    path(
        "users/<int:pk>/activate/",
        views.UserActivationView.as_view(active=True),
        name="user-activate",
    ),
    path(
        "users/<int:pk>/deactivate/",
        views.UserActivationView.as_view(active=False),
        name="user-deactivate",
    ),
    path(
        "users/<int:pk>/reset-password/",
        views.UserResetPasswordView.as_view(),
        name="user-reset-password",
    ),
    path("roles/", views.RoleListCreateView.as_view(), name="roles"),
    path("roles/permissions/", views.PermissionMatrixView.as_view(), name="role-permissions"),
    path("roles/<int:pk>/", views.RoleDetailView.as_view(), name="role-detail"),
    path("permissions/", views.PermissionCatalogView.as_view(), name="permissions"),
]
