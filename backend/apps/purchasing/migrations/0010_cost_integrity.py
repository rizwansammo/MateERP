from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('purchasing', '0009_receiptcostcorrection'), ('inventory', '0006_count_integrity')]
    operations = [migrations.RunSQL('''
    CREATE TRIGGER receipt_cost_immutable BEFORE UPDATE OR DELETE ON purchasing_receiptcostcorrection
    FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
    CREATE FUNCTION mateerp_grni_reconciles() RETURNS trigger AS $$
    DECLARE expected numeric; matched numeric; delta numeric; ledger numeric;
    BEGIN
      SELECT COALESCE(sum(base_value),0) INTO expected FROM purchasing_goodsreceipt WHERE kind='goods';
      SELECT COALESCE(sum(base_delta),0) INTO delta FROM purchasing_receiptcostcorrection;
      SELECT COALESCE(sum(m.base_value),0) INTO matched FROM purchasing_receiptbillmatch m
      JOIN purchasing_goodsreceipt r ON r.id=m.receipt_id JOIN purchasing_vendorbillline l ON l.id=m.bill_line_id
      JOIN purchasing_vendorbill b ON b.id=l.bill_id WHERE r.kind='goods' AND b.status IN ('posted','partially_paid','paid');
      SELECT COALESCE(sum(l.base_credit-l.base_debit),0) INTO ledger FROM accounting_journalline l
      JOIN accounting_journalentry j ON j.id=l.journal_id JOIN accounting_account a ON a.id=l.account_id
      WHERE j.status='posted' AND a.control='grni';
      IF expected+delta-matched<>ledger THEN RAISE EXCEPTION 'Goods receipts and matched bills must reconcile to GRNI'; END IF;
      RETURN NULL;
    END; $$ LANGUAGE plpgsql;
    CREATE FUNCTION mateerp_receipt_match_guard() RETURNS trigger AS $$
    BEGIN
      PERFORM mateerp_financial_lock();
      IF EXISTS(SELECT 1 FROM purchasing_vendorbillline l JOIN purchasing_vendorbill b ON b.id=l.bill_id
        WHERE l.id=OLD.bill_line_id AND b.status IN ('posted','partially_paid','paid','void'))
      THEN RAISE EXCEPTION 'Posted receipt matches are immutable'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER receipt_match_frozen BEFORE UPDATE OR DELETE ON purchasing_receiptbillmatch
    FOR EACH ROW EXECUTE FUNCTION mateerp_receipt_match_guard();
    ''' + '\n'.join(
        f'CREATE CONSTRAINT TRIGGER grni_reconcile_{table} AFTER INSERT OR UPDATE OR DELETE ON {table} '
        'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_grni_reconciles();'
        for table in ['purchasing_goodsreceipt', 'purchasing_receiptcostcorrection', 'purchasing_receiptbillmatch', 'purchasing_vendorbill', 'accounting_journalentry']
    ), '\n'.join(f'DROP TRIGGER grni_reconcile_{t} ON {t};' for t in ['purchasing_goodsreceipt', 'purchasing_receiptcostcorrection', 'purchasing_receiptbillmatch', 'purchasing_vendorbill', 'accounting_journalentry']) + '''
    DROP TRIGGER receipt_cost_immutable ON purchasing_receiptcostcorrection;
    DROP TRIGGER receipt_match_frozen ON purchasing_receiptbillmatch;
    DROP FUNCTION mateerp_grni_reconciles(); DROP FUNCTION mateerp_receipt_match_guard();
    ''')]
