from django.db import migrations

SQL = """
CREATE TRIGGER historical_record_immutable BEFORE UPDATE OR DELETE ON accounting_historicalrecord
FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
CREATE OR REPLACE FUNCTION mateerp_history_treatment_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Retain historical treatment evidence'; END IF;
 IF OLD.status<>'pending' OR ROW(NEW.record_id,NEW.mode,NEW.recognition_date,NEW.reason,NEW.payload,NEW.requested_by_id)
  IS DISTINCT FROM ROW(OLD.record_id,OLD.mode,OLD.recognition_date,OLD.reason,OLD.payload,OLD.requested_by_id)
 THEN RAISE EXCEPTION 'Historical recognition evidence is frozen'; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER historical_treatment_frozen BEFORE UPDATE OR DELETE ON accounting_historicaltreatment
FOR EACH ROW EXECUTE FUNCTION mateerp_history_treatment_guard();
CREATE OR REPLACE FUNCTION mateerp_expense_history_guard() RETURNS trigger AS $$
BEGIN
 IF NEW.original_transaction_date IS NOT NULL AND
   (NEW.original_transaction_date>NEW.expense_date OR
    (NEW.original_transaction_date<>NEW.expense_date AND NEW.recognition_reason=''))
 THEN RAISE EXCEPTION 'Historical recognition requires original date and reason'; END IF;
 IF TG_OP='UPDATE' AND OLD.number IS NOT NULL AND
  ROW(NEW.original_transaction_date,NEW.recognition_reason,NEW.expense_date)
  IS DISTINCT FROM ROW(OLD.original_transaction_date,OLD.recognition_reason,OLD.expense_date)
 THEN RAISE EXCEPTION 'Posted historical expense dates are immutable'; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER expense_historical_dates BEFORE INSERT OR UPDATE ON purchasing_expense
FOR EACH ROW EXECUTE FUNCTION mateerp_expense_history_guard();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0008_historicalrecord_historicaltreatment_and_more"),
        ("purchasing", "0006_expense_original_transaction_date_and_more"),
    ]
    operations = [migrations.RunSQL(SQL, """
    DROP TRIGGER historical_record_immutable ON accounting_historicalrecord;
    DROP TRIGGER historical_treatment_frozen ON accounting_historicaltreatment;
    DROP FUNCTION mateerp_history_treatment_guard();
    DROP TRIGGER expense_historical_dates ON purchasing_expense;
    DROP FUNCTION mateerp_expense_history_guard();
    """)]
