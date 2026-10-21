from django.db import migrations

SQL = """
    CREATE OR REPLACE FUNCTION mateerp_asset_guard() RETURNS trigger AS $$
    DECLARE claimed numeric; source accounting_journalline%ROWTYPE;
    BEGIN
      PERFORM mateerp_financial_lock();
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Retain asset history'; END IF;
      IF TG_OP='UPDATE' THEN
        IF ROW(NEW.tag,NEW.source_line_id,NEW.source_snapshot,NEW.acquisition_date,NEW.recognition_date,NEW.in_service_date,NEW.cost,NEW.journal_id,NEW.depreciation_account_id,NEW.created_by_id,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.tag,OLD.source_line_id,OLD.source_snapshot,OLD.acquisition_date,OLD.recognition_date,OLD.in_service_date,OLD.cost,OLD.journal_id,OLD.depreciation_account_id,OLD.created_by_id,OLD.created_at)
        THEN RAISE EXCEPTION 'Capitalized asset financial identity is immutable'; END IF;
        RETURN NEW;
      END IF;
      SELECT * INTO source FROM accounting_journalline WHERE id=NEW.source_line_id;
      SELECT COALESCE(sum(cost),0) INTO claimed FROM assets_asset a WHERE source_line_id=NEW.source_line_id AND NOT EXISTS(SELECT 1 FROM assets_capitalizationreversal c WHERE c.asset_id=a.id);
      IF NOT EXISTS(SELECT 1 FROM accounting_journalentry j JOIN accounting_account a ON a.id=source.account_id
       WHERE j.id=source.journal_id AND j.status='posted' AND j.source_type IN ('vendor_bill','expense','founder_transaction')
       AND a.control='' AND a.account_type IN ('asset','expense'))
       OR claimed+NEW.cost>source.base_debit-source.base_credit OR EXISTS(SELECT 1 FROM assets_capitalizationreversal c JOIN assets_asset a ON a.id=c.asset_id WHERE a.source_line_id=NEW.source_line_id AND c.date>NEW.recognition_date)
      THEN RAISE EXCEPTION 'Asset acquisition must be a real, unclaimed source debit'; END IF;
      IF NOT EXISTS(SELECT 1 FROM accounting_journalentry WHERE id=NEW.journal_id AND status='posted' AND source_type='asset_event')
      THEN RAISE EXCEPTION 'Capitalization requires its source journal'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;

CREATE FUNCTION mateerp_acquisition_reversal_chronology() RETURNS trigger AS $$
BEGIN
 IF NEW.status='posted' AND NEW.reversal_of_id IS NOT NULL AND EXISTS(
  SELECT 1 FROM assets_asset a JOIN accounting_journalline l ON l.id=a.source_line_id
  LEFT JOIN assets_capitalizationreversal c ON c.asset_id=a.id
  WHERE l.journal_id=NEW.reversal_of_id AND (c.id IS NULL OR c.date>NEW.posting_date))
 THEN RAISE EXCEPTION 'Acquisition reversal requires prior retained capitalization corrections'; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER acquisition_reversal_chronology BEFORE INSERT OR UPDATE ON accounting_journalentry
FOR EACH ROW EXECUTE FUNCTION mateerp_acquisition_reversal_chronology();
"""
REVERSE = """
DROP TRIGGER acquisition_reversal_chronology ON accounting_journalentry;
DROP FUNCTION mateerp_acquisition_reversal_chronology();
    CREATE OR REPLACE FUNCTION mateerp_asset_guard() RETURNS trigger AS $$
    DECLARE claimed numeric; source accounting_journalline%ROWTYPE;
    BEGIN
      PERFORM mateerp_financial_lock();
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Retain asset history'; END IF;
      IF TG_OP='UPDATE' THEN
        IF ROW(NEW.tag,NEW.source_line_id,NEW.source_snapshot,NEW.acquisition_date,NEW.recognition_date,NEW.in_service_date,NEW.cost,NEW.journal_id,NEW.depreciation_account_id,NEW.created_by_id,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.tag,OLD.source_line_id,OLD.source_snapshot,OLD.acquisition_date,OLD.recognition_date,OLD.in_service_date,OLD.cost,OLD.journal_id,OLD.depreciation_account_id,OLD.created_by_id,OLD.created_at)
        THEN RAISE EXCEPTION 'Capitalized asset financial identity is immutable'; END IF;
        RETURN NEW;
      END IF;
      SELECT * INTO source FROM accounting_journalline WHERE id=NEW.source_line_id;
      SELECT COALESCE(sum(cost),0) INTO claimed FROM assets_asset a WHERE source_line_id=NEW.source_line_id AND NOT EXISTS(SELECT 1 FROM assets_capitalizationreversal c WHERE c.asset_id=a.id);
      IF NOT EXISTS(SELECT 1 FROM accounting_journalentry j JOIN accounting_account a ON a.id=source.account_id
       WHERE j.id=source.journal_id AND j.status='posted' AND j.source_type IN ('vendor_bill','expense','founder_transaction')
       AND a.control='' AND a.account_type IN ('asset','expense'))
       OR claimed+NEW.cost>source.base_debit-source.base_credit
      THEN RAISE EXCEPTION 'Asset acquisition must be a real, unclaimed source debit'; END IF;
      IF NOT EXISTS(SELECT 1 FROM accounting_journalentry WHERE id=NEW.journal_id AND status='posted' AND source_type='asset_event')
      THEN RAISE EXCEPTION 'Capitalization requires its source journal'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
"""

class Migration(migrations.Migration):
    dependencies = [("assets", "0004_capitalization_correction_integrity")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
