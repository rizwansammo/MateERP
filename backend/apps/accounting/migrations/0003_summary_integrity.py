from django.db import migrations


SQL = r"""
CREATE FUNCTION mateerp_summary_guard() RETURNS trigger AS $$
BEGIN
  PERFORM mateerp_financial_lock();
  IF EXISTS(SELECT 1 FROM accounting_account WHERE parent_id=NEW.id AND account_type<>NEW.account_type) THEN
    RAISE EXCEPTION 'Summary and child account types must agree' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND ROW(NEW.code,NEW.account_type,NEW.normal_side,NEW.parent_id,NEW.currency,NEW.subtype,NEW.control,NEW.is_postable)
       IS DISTINCT FROM ROW(OLD.code,OLD.account_type,OLD.normal_side,OLD.parent_id,OLD.currency,OLD.subtype,OLD.control,OLD.is_postable)
     AND EXISTS(WITH RECURSIVE descendants AS (
       SELECT id FROM accounting_account WHERE id=OLD.id
       UNION ALL SELECT a.id FROM accounting_account a JOIN descendants d ON a.parent_id=d.id
     ) SELECT 1 FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id
       WHERE l.account_id IN (SELECT id FROM descendants) AND j.status='posted') THEN
    RAISE EXCEPTION 'Posted descendant history locks summary meaning' USING ERRCODE='23514';
  END IF;
  IF NEW.control<>'' AND (NOT NEW.is_postable OR
    (NEW.control='fx_gain' AND NEW.account_type<>'revenue') OR
    (NEW.control='fx_loss' AND NEW.account_type<>'expense') OR
    (NEW.control='retained_earnings' AND NEW.account_type<>'equity') OR
    NEW.control NOT IN ('fx_gain','fx_loss','retained_earnings')) THEN
    RAISE EXCEPTION 'Invalid control account' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER summary_guard BEFORE INSERT OR UPDATE ON accounting_account FOR EACH ROW EXECUTE FUNCTION mateerp_summary_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("accounting", "0002_integrity")]
    operations = [migrations.RunSQL(SQL)]
