from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0007_procurementevidence")]
    operations = [migrations.RunSQL(
        "CREATE TRIGGER procurement_evidence_immutable BEFORE UPDATE OR DELETE ON "
        "purchasing_procurementevidence FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();",
        "DROP TRIGGER procurement_evidence_immutable ON purchasing_procurementevidence;",
    )]
