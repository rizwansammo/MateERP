from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
        ("core", "0001_append_only_trigger_function"),
    ]
    operations = [migrations.RunSQL(
        "CREATE TRIGGER catalog_price_append_only BEFORE UPDATE OR DELETE ON "
        "catalog_pricerevision FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();",
        "DROP TRIGGER catalog_price_append_only ON catalog_pricerevision;",
    )]
