from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION mateerp_grni_reconciles() RETURNS trigger AS $$
DECLARE expected numeric; matched numeric; delta numeric; returned numeric; ledger numeric;
BEGIN
 SELECT COALESCE(sum(base_value),0) INTO expected FROM purchasing_goodsreceipt WHERE kind='goods';
 SELECT COALESCE(sum(base_delta),0) INTO delta FROM purchasing_receiptcostcorrection;
 SELECT COALESCE(sum(base_value),0) INTO returned FROM purchasing_supplierreturn;
 SELECT COALESCE(sum(m.base_value),0) INTO matched FROM purchasing_receiptbillmatch m
 JOIN purchasing_goodsreceipt r ON r.id=m.receipt_id JOIN purchasing_vendorbillline l ON l.id=m.bill_line_id
 JOIN purchasing_vendorbill b ON b.id=l.bill_id WHERE r.kind='goods' AND b.status IN ('posted','partially_paid','paid');
 SELECT COALESCE(sum(l.base_credit-l.base_debit),0) INTO ledger FROM accounting_journalline l
 JOIN accounting_journalentry j ON j.id=l.journal_id JOIN accounting_account a ON a.id=l.account_id
 WHERE j.status='posted' AND a.control='grni';
 IF expected+delta-returned-matched<>ledger THEN RAISE EXCEPTION 'Receipts, returns and matching must reconcile to GRNI'; END IF;
 RETURN NULL;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER supplier_return_immutable BEFORE UPDATE OR DELETE ON purchasing_supplierreturn
FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
CREATE FUNCTION mateerp_supplier_return_guard() RETURNS trigger AS $$
DECLARE acquired numeric; returned numeric; matched numeric;
BEGIN
 PERFORM mateerp_financial_lock();
 SELECT quantity INTO acquired FROM purchasing_goodsreceipt WHERE id=NEW.receipt_id AND kind='goods';
 SELECT COALESCE(sum(quantity),0) INTO returned FROM purchasing_supplierreturn WHERE receipt_id=NEW.receipt_id;
 IF acquired IS NULL OR NEW.quantity+returned>acquired OR EXISTS(
  SELECT 1 FROM purchasing_receiptbillmatch m JOIN purchasing_vendorbillline l ON l.id=m.bill_line_id
  JOIN purchasing_vendorbill b ON b.id=l.bill_id WHERE m.receipt_id=NEW.receipt_id AND b.status NOT IN ('void','cancelled'))
 THEN RAISE EXCEPTION 'Supplier returns require unreturned, unmatched goods'; END IF;
 IF NOT EXISTS(SELECT 1 FROM inventory_movement m JOIN purchasing_goodsreceipt r ON r.id=NEW.receipt_id
  JOIN purchasing_purchaseorderline l ON l.id=r.order_line_id JOIN accounting_journalentry j ON j.id=NEW.journal_id
  WHERE m.id=NEW.movement_id AND m.item_id=l.item_id AND m.original_id=r.movement_id AND m.kind='supplier_return'
  AND m.quantity=-NEW.quantity AND m.base_value=-NEW.inventory_value AND m.date=NEW.date
  AND m.journal_id=NEW.journal_id AND j.status='posted' AND j.source_type='supplier_return'
  AND NEW.variance=NEW.inventory_value-NEW.base_value)
 THEN RAISE EXCEPTION 'Supplier return must retain its matching source cost and movement'; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER supplier_return_valid BEFORE INSERT ON purchasing_supplierreturn
FOR EACH ROW EXECUTE FUNCTION mateerp_supplier_return_guard();
CREATE FUNCTION mateerp_match_available_guard() RETURNS trigger AS $$
DECLARE acquired numeric; returned numeric; used numeric;
BEGIN
 PERFORM mateerp_financial_lock();
 IF NOT EXISTS(SELECT 1 FROM purchasing_vendorbillline l JOIN purchasing_vendorbill b ON b.id=l.bill_id
  WHERE l.id=NEW.bill_line_id AND b.status='draft')
 THEN RAISE EXCEPTION 'Only draft bill lines can acquire new receipt matches'; END IF;
 SELECT quantity INTO acquired FROM purchasing_goodsreceipt WHERE id=NEW.receipt_id;
 SELECT COALESCE(sum(quantity),0) INTO returned FROM purchasing_supplierreturn WHERE receipt_id=NEW.receipt_id;
 SELECT COALESCE(sum(m.quantity),0) INTO used FROM purchasing_receiptbillmatch m
 JOIN purchasing_vendorbillline l ON l.id=m.bill_line_id JOIN purchasing_vendorbill b ON b.id=l.bill_id
 WHERE m.receipt_id=NEW.receipt_id AND b.status NOT IN ('void','cancelled');
 IF NEW.quantity+used>acquired-returned THEN RAISE EXCEPTION 'Matching cannot reuse returned goods'; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER receipt_match_available BEFORE INSERT ON purchasing_receiptbillmatch
FOR EACH ROW EXECUTE FUNCTION mateerp_match_available_guard();
CREATE CONSTRAINT TRIGGER grni_reconcile_returns AFTER INSERT ON purchasing_supplierreturn
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_grni_reconciles();
"""
REVERSE = """
DROP TRIGGER grni_reconcile_returns ON purchasing_supplierreturn;
DROP TRIGGER supplier_return_immutable ON purchasing_supplierreturn;
DROP TRIGGER supplier_return_valid ON purchasing_supplierreturn;
DROP TRIGGER receipt_match_available ON purchasing_receiptbillmatch;
DROP FUNCTION mateerp_supplier_return_guard(); DROP FUNCTION mateerp_match_available_guard();
CREATE OR REPLACE FUNCTION mateerp_grni_reconciles() RETURNS trigger AS $$
DECLARE expected numeric; matched numeric; delta numeric; returned numeric; ledger numeric;
BEGIN
 SELECT COALESCE(sum(base_value),0) INTO expected FROM purchasing_goodsreceipt WHERE kind='goods';
 SELECT COALESCE(sum(base_delta),0) INTO delta FROM purchasing_receiptcostcorrection;
 returned := 0;
 SELECT COALESCE(sum(m.base_value),0) INTO matched FROM purchasing_receiptbillmatch m
 JOIN purchasing_goodsreceipt r ON r.id=m.receipt_id JOIN purchasing_vendorbillline l ON l.id=m.bill_line_id
 JOIN purchasing_vendorbill b ON b.id=l.bill_id WHERE r.kind='goods' AND b.status IN ('posted','partially_paid','paid');
 SELECT COALESCE(sum(l.base_credit-l.base_debit),0) INTO ledger FROM accounting_journalline l
 JOIN accounting_journalentry j ON j.id=l.journal_id JOIN accounting_account a ON a.id=l.account_id
 WHERE j.status='posted' AND a.control='grni';
 IF expected+delta-returned-matched<>ledger THEN RAISE EXCEPTION 'Receipts, returns and matching must reconcile to GRNI'; END IF;
 RETURN NULL;
END; $$ LANGUAGE plpgsql;
"""

class Migration(migrations.Migration):
    dependencies = [("purchasing", "0011_supplier_return")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
