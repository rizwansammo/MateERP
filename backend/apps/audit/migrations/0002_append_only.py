from django.db import migrations

CREATE = """
CREATE TRIGGER audit_event_append_only
BEFORE UPDATE OR DELETE ON audit_auditevent
FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
"""
DROP = "DROP TRIGGER IF EXISTS audit_event_append_only ON audit_auditevent;"


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
        ("core", "0001_append_only_trigger_function"),
    ]
    operations = [migrations.RunSQL(CREATE, DROP)]
