from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class Permission(models.Model):
    """Application permission catalog (synced from ``catalog.PERMISSIONS``)."""

    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=120)
    category = models.CharField(max_length=32)
    description = models.CharField(max_length=300, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return self.code


class Role(models.Model):
    """An application access role (not an employment position).

    Exactly one role is the Administrator role: it always holds every
    permission, cannot be edited or deactivated, and protects the company
    from locking itself out.
    """

    key = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    is_system = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_admin", "-is_system", "name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="role_name_ci_unique"),
            models.UniqueConstraint(
                fields=["is_admin"], condition=Q(is_admin=True), name="single_admin_role"
            ),
            models.CheckConstraint(
                condition=Q(is_admin=False) | Q(is_active=True), name="admin_role_always_active"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    """Application user. Identity and access only — no HR data (that is MateHR)."""

    role = models.ForeignKey(
        Role, null=True, blank=True, on_delete=models.PROTECT, related_name="users"
    )
    must_change_password = models.BooleanField(default=False)
    preferences = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "accounts_user"
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            models.UniqueConstraint(Lower("username"), name="user_username_ci_unique"),
            models.UniqueConstraint(
                Lower("email"), condition=~Q(email=""), name="user_email_ci_unique"
            ),
        ]

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username


class LoginFailure(models.Model):
    """One failed sign-in attempt, used for sliding-window throttling.

    ``identifier`` is the normalised login name as typed (it may not match a
    real account). Rows older than a day are pruned automatically.
    """

    identifier = models.CharField(max_length=254)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["identifier", "created_at"], name="loginfail_ident_idx"),
            models.Index(fields=["ip_address", "created_at"], name="loginfail_ip_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.identifier} @ {self.created_at:%Y-%m-%d %H:%M:%S}"
