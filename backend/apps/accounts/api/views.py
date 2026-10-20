from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import IsActiveUser, requires, requires_any
from apps.accounts.models import Permission, Role, User
from apps.accounts.services import auth as auth_services
from apps.accounts.services import roles as role_services
from apps.accounts.services import users as user_services
from apps.audit.services import diff, record

from . import serializers as s

# --- Authentication -----------------------------------------------------------


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Issue the CSRF cookie. Call before the first state-changing request."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer("Csrf", {"csrf_token": serializers.CharField()}), tags=["auth"]
    )
    def get(self, request: Request) -> Response:
        return Response({"csrf_token": get_token(request)})


class SessionView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=s.SessionSerializer, tags=["auth"])
    def get(self, request: Request) -> Response:
        user = request.user if request.user.is_authenticated else None
        response = Response(
            {
                "authenticated": user is not None,
                "user": s.CurrentUserSerializer(user).data if user else None,
            }
        )
        response["Cache-Control"] = "no-store"
        return response


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=s.LoginSerializer, responses=s.CurrentUserSerializer, tags=["auth"])
    def post(self, request: Request) -> Response:
        data = s.LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = auth_services.sign_in(request._request, **data.validated_data)
        return Response(s.CurrentUserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        auth_services.sign_out(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    allow_password_change_required = True

    @extend_schema(responses=s.CurrentUserSerializer, tags=["auth"])
    def get(self, request: Request) -> Response:
        return Response(s.CurrentUserSerializer(request.user).data)

    @extend_schema(
        request=s.ProfileUpdateSerializer, responses=s.CurrentUserSerializer, tags=["auth"]
    )
    def patch(self, request: Request) -> Response:
        data = s.ProfileUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        user: User = request.user

        if (
            "email" in values
            and User.objects.exclude(pk=user.pk).filter(email__iexact=values["email"]).exists()
        ):
            raise serializers.ValidationError({"email": ["Another user already uses this email."]})

        before = {"first_name": user.first_name, "last_name": user.last_name, "email": user.email}
        for field in ("first_name", "last_name", "email"):
            if field in values:
                setattr(user, field, values[field])
        if "preferences" in values:
            user.preferences = {**(user.preferences or {}), **values["preferences"]}
        user.save()
        old, new = diff(
            before,
            {"first_name": user.first_name, "last_name": user.last_name, "email": user.email},
        )
        if new:
            record(
                "user.profile_updated", request=request._request, target=user, before=old, after=new
            )
        return Response(s.CurrentUserSerializer(user).data)


class PasswordChangeView(APIView):
    allow_password_change_required = True

    @extend_schema(
        request=s.PasswordChangeSerializer, responses=s.CurrentUserSerializer, tags=["auth"]
    )
    def post(self, request: Request) -> Response:
        data = s.PasswordChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        auth_services.change_password(request._request, **data.validated_data)
        return Response(s.CurrentUserSerializer(request.user).data)


# --- Users ---------------------------------------------------------------------

USER_ORDERING = {
    "name": ("first_name", "last_name", "username"),
    "username": ("username",),
    "email": ("email",),
    "role": ("role__name", "username"),
    "last_login": ("last_login",),
    "date_joined": ("date_joined",),
}


@extend_schema(tags=["users"])
class UserListCreateView(generics.ListAPIView):
    permission_classes = [IsActiveUser, requires("users.manage")]
    serializer_class = s.UserSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str),
            OpenApiParameter("role", int),
            OpenApiParameter("status", str, enum=["active", "inactive"]),
            OpenApiParameter("ordering", str),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = User.objects.select_related("role")
        params = self.request.query_params
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        if (role := params.get("role")) and role.isdigit():
            qs = qs.filter(role_id=int(role))
        if params.get("status") in ("active", "inactive"):
            qs = qs.filter(is_active=params["status"] == "active")
        ordering = params.get("ordering", "name")
        descending = ordering.startswith("-")
        fields = USER_ORDERING.get(ordering.lstrip("-"), USER_ORDERING["name"])
        return qs.order_by(*(f"-{f}" if descending else f for f in fields), "pk")

    @extend_schema(request=s.UserCreateSerializer, responses={201: s.TemporaryPasswordSerializer})
    def post(self, request: Request) -> Response:
        data = s.UserCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user, password = user_services.create_user(request._request, **data.validated_data)
        response = Response(
            {"user": s.UserSerializer(user).data, "temporary_password": password},
            status=status.HTTP_201_CREATED,
        )
        response["Cache-Control"] = "no-store"
        return response


@extend_schema(tags=["users"])
class UserDetailView(APIView):
    permission_classes = [IsActiveUser, requires("users.manage")]

    @extend_schema(responses=s.UserSerializer)
    def get(self, request: Request, pk: int) -> Response:
        user = get_object_or_404(User.objects.select_related("role"), pk=pk)
        return Response(s.UserSerializer(user).data)

    @extend_schema(request=s.UserUpdateSerializer, responses=s.UserSerializer)
    def patch(self, request: Request, pk: int) -> Response:
        user = get_object_or_404(User, pk=pk)
        data = s.UserUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        user = user_services.update_user(request._request, user, data=data.validated_data)
        return Response(s.UserSerializer(user).data)


@extend_schema(tags=["users"], request=None, responses=s.UserSerializer)
class UserActivationView(APIView):
    permission_classes = [IsActiveUser, requires("users.manage")]
    active = True

    def post(self, request: Request, pk: int) -> Response:
        user = get_object_or_404(User, pk=pk)
        user = user_services.set_active(request._request, user, active=self.active)
        return Response(s.UserSerializer(User.objects.select_related("role").get(pk=user.pk)).data)


@extend_schema(tags=["users"], request=None, responses=s.TemporaryPasswordSerializer)
class UserResetPasswordView(APIView):
    permission_classes = [IsActiveUser, requires("users.manage")]

    def post(self, request: Request, pk: int) -> Response:
        user = get_object_or_404(User.objects.select_related("role"), pk=pk)
        password = user_services.reset_password(request._request, user)
        response = Response({"user": s.UserSerializer(user).data, "temporary_password": password})
        response["Cache-Control"] = "no-store"
        return response


# --- Roles & permissions -----------------------------------------------------------


def roles_queryset():
    return (
        Role.objects.prefetch_related("permissions")
        .annotate(user_count=Count("users", filter=Q(users__is_active=True)))
        .order_by("-is_admin", "-is_system", "name")
    )


@extend_schema(tags=["roles"])
class RoleListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsActiveUser(), requires("roles.manage")()]
        return [
            IsActiveUser(),
            requires_any("users.manage", "roles.manage", "permissions.manage")(),
        ]

    @extend_schema(responses=s.RoleSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(s.RoleSerializer(roles_queryset(), many=True).data)

    @extend_schema(request=s.RoleCreateSerializer, responses={201: s.RoleSerializer})
    def post(self, request: Request) -> Response:
        data = s.RoleCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        role = role_services.create_role(
            request._request,
            name=values["name"],
            description=values["description"],
            permissions=set(values["permissions"]),
        )
        return Response(
            s.RoleSerializer(roles_queryset().get(pk=role.pk)).data, status=status.HTTP_201_CREATED
        )


@extend_schema(tags=["roles"])
class RoleDetailView(APIView):
    permission_classes = [IsActiveUser, requires("roles.manage")]

    @extend_schema(request=s.RoleUpdateSerializer, responses=s.RoleSerializer)
    def patch(self, request: Request, pk: int) -> Response:
        role = get_object_or_404(Role, pk=pk)
        data = s.RoleUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        role_services.update_role(request._request, role, data=data.validated_data)
        return Response(s.RoleSerializer(roles_queryset().get(pk=pk)).data)


@extend_schema(tags=["roles"])
class PermissionMatrixView(APIView):
    permission_classes = [IsActiveUser, requires("permissions.manage")]

    @extend_schema(request=s.PermissionMatrixSerializer, responses=s.RoleSerializer(many=True))
    def post(self, request: Request) -> Response:
        data = s.PermissionMatrixSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        role_services.set_role_permissions(request._request, data.validated_data["changes"])
        return Response(s.RoleSerializer(roles_queryset(), many=True).data)


@extend_schema(tags=["roles"])
class PermissionCatalogView(APIView):
    @extend_schema(responses=s.PermissionSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(s.PermissionSerializer(Permission.objects.all(), many=True).data)
