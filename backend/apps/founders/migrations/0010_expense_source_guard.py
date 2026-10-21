from django.db import migrations


SQL = r"""
CREATE FUNCTION mateerp_founder_expense_identity_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF EXISTS(SELECT 1 FROM founders_corporatetransaction WHERE expense_id=OLD.id) AND
  (to_jsonb(NEW)-ARRAY['number','status','journal_id','base_total','exchange_rate','posted_by_id','posted_at','void_journal_id','void_reason'])
  IS DISTINCT FROM
  (to_jsonb(OLD)-ARRAY['number','status','journal_id','base_total','exchange_rate','posted_by_id','posted_at','void_journal_id','void_reason']) THEN
  RAISE EXCEPTION 'Founder-funded expense identity is frozen with its source' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER founder_expense_identity_guard BEFORE UPDATE ON purchasing_expense FOR EACH ROW EXECUTE FUNCTION mateerp_founder_expense_identity_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("founders", "0009_founderobligation_recovery_origin")]
    operations = [migrations.RunSQL(SQL)]
