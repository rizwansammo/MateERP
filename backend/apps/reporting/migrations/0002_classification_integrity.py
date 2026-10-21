from django.db import migrations


class Migration(migrations.Migration):
    dependencies=[('reporting','0001_initial')]
    operations=[migrations.RunSQL('''
    CREATE TRIGGER cash_flow_review_immutable BEFORE UPDATE OR DELETE ON reporting_cashflowreview
    FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
    CREATE FUNCTION mateerp_cash_classification_guard() RETURNS trigger AS $$
    DECLARE cash numeric; allocated numeric;
    BEGIN
      PERFORM mateerp_financial_lock();
      SELECT COALESCE(sum(l.base_debit-l.base_credit),0) INTO cash FROM accounting_journalline l
      JOIN banking_bankaccount b ON b.gl_account_id=l.account_id
      JOIN accounting_journalentry j ON j.id=l.journal_id
      WHERE l.journal_id=NEW.journal_id AND j.status='posted' AND j.kind<>'transfer';
      SELECT COALESCE(sum((a->>'amount')::numeric),0) INTO allocated FROM jsonb_array_elements(NEW.allocations) a;
      IF cash=0 OR cash<>allocated OR jsonb_array_length(NEW.allocations)=0 OR EXISTS(
        SELECT 1 FROM jsonb_array_elements(NEW.allocations) a WHERE a->>'category' NOT IN
        ('operating','investing','financing','opening_cutover','unclassified'))
      THEN RAISE EXCEPTION 'Cash classification must allocate its exact posted movement'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER cash_flow_review_valid BEFORE INSERT ON reporting_cashflowreview
    FOR EACH ROW EXECUTE FUNCTION mateerp_cash_classification_guard();
    ''','''
    DROP TRIGGER cash_flow_review_immutable ON reporting_cashflowreview;
    DROP TRIGGER cash_flow_review_valid ON reporting_cashflowreview;
    DROP FUNCTION mateerp_cash_classification_guard();
    ''')]
