import re

from rest_framework import serializers

from apps.accounts.authorization import get_permission_codes
from apps.accounts.catalog import CATEGORIES
from apps.accounts.models import Permission, Role, User

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,150}$")
LANDING_PAGES = ("/dashboard", "/settings/company", "/settings/users", "/settings/branding")


def initials(user: User) -> str:
    parts = [p for p in (user.first_name, user.last_name) if p] or [user.username]
    return "".join(p[0] for p in parts)[:2].upper()


class RoleRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "is_admin"]
        read_only_fields = fields


class CurrentUserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    initials = serializers.SerializerMethodField()
    role = RoleRefSerializer(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "initials",
            "role",
            "permissions",
            "must_change_password",
            "preferences",
            "last_login",
        ]
        read_only_fields = fields

    def get_initials(self, obj: User) -> str:
        return initials(obj)

    def get_permissions(self, obj: User) -> list[str]:
        return sorted(get_permission_codes(obj))


class SessionSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    user = CurrentUserSerializer(allow_null=True)


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(
        max_length=256, trim_whitespace=False, style={"input_type": "password"}
    )
    remember = serializers.BooleanField(default=False)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=256, trim_whitespace=False)
    new_password = serializers.CharField(max_length=256, trim_whitespace=False)


class PreferencesSerializer(serializers.Serializer):
    theme = serializers.ChoiceField(choices=["light", "dark"], required=False)
    sidebar = serializers.ChoiceField(choices=["full", "compact"], required=False)
    rows_per_page = serializers.ChoiceField(choices=[10, 25, 50], required=False)
    landing_page = serializers.ChoiceField(choices=LANDING_PAGES, required=False)


class ProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=254, required=False)
    preferences = PreferencesSerializer(required=False)


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    initials = serializers.SerializerMethodField()
    role = RoleRefSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "initials",
            "role",
            "is_active",
            "must_change_password",
            "last_login",
            "date_joined",
        ]
        read_only_fields = fields

    def get_initials(self, obj: User) -> str:
        return initials(obj)


class UserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    first_name = serializers.CharField(max_length=150, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, allow_blank=True, default="")
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())
    is_active = serializers.BooleanField(default=True)

    def validate_username(self, value: str) -> str:
        if not USERNAME_PATTERN.match(value):
            raise serializers.ValidationError(
                "Use 3–150 letters, digits, dots, hyphens or underscores."
            )
        return value


class UserUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    email = serializers.EmailField(max_length=254, required=False)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), required=False)


class TemporaryPasswordSerializer(serializers.Serializer):
    user = UserSerializer()
    temporary_password = serializers.CharField(
        help_text="Shown once. Never stored in plain text and cannot be retrieved later."
    )


class PermissionSerializer(serializers.ModelSerializer):
    category_label = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ["code", "label", "category", "category_label", "description"]
        read_only_fields = fields

    def get_category_label(self, obj: Permission) -> str:
        return CATEGORIES.get(obj.category, obj.category)


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = [
            "id",
            "key",
            "name",
            "description",
            "is_system",
            "is_admin",
            "is_active",
            "permissions",
            "user_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_permissions(self, obj: Role) -> list[str]:
        if obj.is_admin:
            return sorted(Permission.objects.values_list("code", flat=True))
        return sorted(p.code for p in obj.permissions.all())


class RoleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=80)
    description = serializers.CharField(max_length=300, allow_blank=True, default="")
    permissions = serializers.ListField(child=serializers.CharField(max_length=64), default=list)


class RoleUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=80, required=False)
    description = serializers.CharField(max_length=300, allow_blank=True, required=False)
    is_active = serializers.BooleanField(required=False)


class PermissionMatrixSerializer(serializers.Serializer):
    changes = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField(max_length=64)),
        help_text="Role id → complete list of permission codes for that role.",
    )

    def validate_changes(self, value: dict) -> dict[int, set[str]]:
        try:
            return {int(k): set(v) for k, v in value.items()}
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError("Role ids must be integers.") from exc
