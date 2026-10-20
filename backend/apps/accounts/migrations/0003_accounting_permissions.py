from django.db import migrations


def add_permissions(apps, schema_editor):
    permission = apps.get_model("accounts", "Permission")
    # Administrator access is derived from the complete catalog. Preserve every
    # existing non-admin/custom role assignment; grant these deliberately in UI.
    for code, label, order in (
        ("accounting.approve", "Approve financial adjustments", 10),
        ("accounting.periods.manage", "Close and reopen accounting periods", 11),
    ):
        permission.objects.get_or_create(code=code, defaults={"label": label, "category": "finance", "sort_order": order})


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_permission_user_must_change_password_and_more")]
    operations = [migrations.RunPython(add_permissions, migrations.RunPython.noop)]
