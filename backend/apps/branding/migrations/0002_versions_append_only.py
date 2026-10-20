from django.db import migrations

CREATE = """
CREATE TRIGGER branding_version_append_only
BEFORE UPDATE OR DELETE ON branding_brandingversion
FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
"""
DROP = "DROP TRIGGER IF EXISTS branding_version_append_only ON branding_brandingversion;"


class Migration(migrations.Migration):
    dependencies = [
        ("branding", "0001_initial"),
        ("core", "0001_append_only_trigger_function"),
    ]
    operations = [migrations.RunSQL(CREATE, DROP)]
