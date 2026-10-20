"""Idempotent setup of the permission catalog and default roles (runs after migrate)."""

from django.db import transaction

from .catalog import DEFAULT_ROLES, PERMISSIONS


@transaction.atomic
def ensure_permission_catalog(**kwargs) -> None:
    from .models import Permission, Role

    for index, definition in enumerate(PERMISSIONS):
        Permission.objects.update_or_create(
            code=definition.code,
            defaults={
                "label": definition.label,
                "category": definition.category,
                "description": definition.description,
                "sort_order": index,
            },
        )

    # Default roles are created once with their default permission sets.
    # Later edits by administrators are preserved.
    for role_def in DEFAULT_ROLES:
        role, created = Role.objects.get_or_create(
            key=role_def.key,
            defaults={
                "name": role_def.name,
                "description": role_def.description,
                "is_system": True,
                "is_admin": role_def.is_admin,
            },
        )
        if created and not role_def.is_admin:
            role.permissions.set(Permission.objects.filter(code__in=role_def.permissions))
