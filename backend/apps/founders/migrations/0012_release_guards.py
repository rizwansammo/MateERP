from importlib import import_module

from django.db import migrations


def replacement_functions():
    original = import_module("apps.founders.migrations.0008_planning_identity_guards").SQL
    designation = original.split("CREATE TRIGGER funding_designation_guard")[0]
    designation = designation.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")
    designation = designation.replace(
        "(SELECT COALESCE(SUM(amount),0) FROM founders_fundingdesignation WHERE receipt_id=t.id)>t.amount",
        """(SELECT COALESCE(SUM(amount),0) FROM founders_fundingdesignation WHERE receipt_id=t.id)
   -(SELECT COALESCE(SUM(r.amount),0) FROM founders_fundingrelease r JOIN founders_fundingdesignation d ON d.id=r.designation_id WHERE d.receipt_id=t.id)>t.amount""",
    )
    original = import_module("apps.founders.migrations.0007_funding_history_guards").SQL
    consumption = "CREATE OR REPLACE FUNCTION mateerp_funding_consumption_guard" + original.split(
        "CREATE FUNCTION mateerp_funding_consumption_guard"
    )[1].split("CREATE TRIGGER funding_consumption_guard")[0]
    consumption = consumption.replace(
        "IF used+NEW.amount>d.amount", """used:=used+(SELECT COALESCE(SUM(amount),0) FROM founders_fundingrelease WHERE designation_id=d.id);
  IF used+NEW.amount>d.amount""",
    )
    return designation + consumption


SQL = r"""
CREATE FUNCTION mateerp_funding_release_guard() RETURNS trigger AS $$
DECLARE d founders_fundingdesignation; used numeric;
BEGIN
 PERFORM mateerp_financial_lock();
 SELECT * INTO d FROM founders_fundingdesignation WHERE id=NEW.designation_id FOR UPDATE;
 SELECT COALESCE(SUM(amount),0) INTO used FROM founders_fundingrelease WHERE designation_id=d.id;
 used:=used+(SELECT COALESCE(SUM(c.amount),0) FROM founders_fundingconsumption c WHERE c.designation_id=d.id AND c.reverses_id IS NULL AND NOT EXISTS(SELECT 1 FROM founders_fundingconsumption r WHERE r.reverses_id=c.id));
 IF NEW.reason='' OR used+NEW.amount>d.amount THEN
  RAISE EXCEPTION 'Only retained unused funding can be released with a reason' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER funding_release_guard BEFORE INSERT ON founders_fundingrelease FOR EACH ROW EXECUTE FUNCTION mateerp_funding_release_guard();
CREATE TRIGGER funding_release_append_only BEFORE UPDATE OR DELETE ON founders_fundingrelease FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
"""


class Migration(migrations.Migration):
    dependencies = [("founders", "0011_reservedesignationtransfer_amount_and_more")]
    operations = [migrations.RunSQL(replacement_functions() + SQL)]
