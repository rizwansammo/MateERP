"""Add operational purposes without changing the meaning of existing accounts."""
from importlib import import_module

from django.db import migrations

PREVIOUS = import_module("apps.accounting.migrations.0006_founder_controls").NEW
ASSETS = "'inventory','unbilled_revenue','fixed_assets','accumulated_depreciation','asset_acquisition'"
LIABILITIES = "'grni','deferred_revenue'"
NEW = PREVIOUS.replace(
    "NEW.control NOT IN",
    f"(NEW.control IN ({ASSETS}) AND NEW.account_type<>'asset') OR "
    f"(NEW.control IN ({LIABILITIES}) AND NEW.account_type<>'liability') OR "
    f"(NEW.control IN ({ASSETS},{LIABILITIES}) AND NEW.currency<>'') OR NEW.control NOT IN",
).replace(
    "'fx_gain','fx_loss','retained_earnings'",
    f"{ASSETS},{LIABILITIES},'fx_gain','fx_loss','retained_earnings'",
)


class Migration(migrations.Migration):
    dependencies = [("accounting", "0006_founder_controls")]
    operations = [migrations.RunSQL(NEW, PREVIOUS)]
