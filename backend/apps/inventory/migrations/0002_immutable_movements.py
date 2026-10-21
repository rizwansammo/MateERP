from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial"), ("core", "0001_append_only_trigger_function")]
    operations = [migrations.RunSQL(
        "CREATE TRIGGER inventory_movement_append_only BEFORE UPDATE OR DELETE ON "
        "inventory_movement FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();",
        "DROP TRIGGER inventory_movement_append_only ON inventory_movement;",
    )]
