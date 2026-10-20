from django.db import migrations

PERMISSIONS = (
    ("sales.manage", "Manage customers and sales orders"),
    ("invoices.issue", "Approve and issue invoices"),
    ("payments.record", "Record client payments"),
    ("credit_notes.manage", "Manage credit notes and refunds"),
    ("vendors.manage", "Manage vendors"),
    ("bills.manage", "Manage vendor bills"),
    ("vendor_payments.manage", "Pay vendors"),
    ("documents.client.view", "View client documents"),
    ("documents.vendor.view", "View vendor documents"),
    ("documents.manage", "Upload and archive documents"),
)


def add_permissions(apps, schema_editor):
    permission = apps.get_model("accounts", "Permission")
    # Administrator access derives from the full catalog. Existing non-admin and
    # custom roles are left unchanged; administrators grant these deliberately.
    for order, (code, label) in enumerate(PERMISSIONS, start=20):
        permission.objects.get_or_create(
            code=code, defaults={"label": label, "category": "finance", "sort_order": order}
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_accounting_permissions")]
    operations = [migrations.RunPython(add_permissions, migrations.RunPython.noop)]
