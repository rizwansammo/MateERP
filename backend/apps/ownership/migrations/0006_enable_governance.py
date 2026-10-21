from django.db import migrations


def enable_governance(apps, schema_editor):
    Policy = apps.get_model("approvals", "ApprovalPolicy")
    Event = apps.get_model("audit", "AuditEvent")
    for policy in Policy.objects.filter(category="ownership_changes"):
        before = {
            key: getattr(policy, key) for key in ("is_required", "is_active", "allow_self_approval")
        }
        after = {"is_required": True, "is_active": True, "allow_self_approval": False}
        if before != after:
            Policy.objects.filter(pk=policy.pk).update(**after)
            Event.objects.create(
                action="ownership.governance_enabled",
                target_type="approvals.approvalpolicy",
                target_id=str(policy.pk),
                before=before,
                after=after,
                reason="Phase 5 requires independent ownership review and affected-party authorization.",
            )


class Migration(migrations.Migration):
    dependencies = [("ownership", "0005_governance_guards")]
    operations = [migrations.RunPython(enable_governance, migrations.RunPython.noop)]
