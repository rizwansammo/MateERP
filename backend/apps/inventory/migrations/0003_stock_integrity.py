from django.db import migrations

SQL = """
CREATE FUNCTION mateerp_stock_insert_guard() RETURNS trigger AS $$
DECLARE qty numeric; value numeric; latest date; unit_fraction boolean; journal_value numeric;
BEGIN
 PERFORM mateerp_financial_lock();
 IF NOT EXISTS(SELECT 1 FROM catalog_itemprofile p JOIN inventory_location l ON l.id=NEW.location_id
   JOIN sales_billingitem i ON i.id=p.item_id JOIN accounting_account a ON a.id=p.inventory_account_id
   WHERE p.item_id=NEW.item_id AND p.kind='stock' AND l.is_active AND i.is_active AND a.control='inventory')
 THEN RAISE EXCEPTION 'Stock requires an active tracked item, location and control'; END IF;
 SELECT u.allows_fraction INTO unit_fraction FROM catalog_itemprofile p
 JOIN catalog_unit u ON u.id=p.unit_id WHERE p.item_id=NEW.item_id;
 IF NOT unit_fraction AND NEW.quantity<>trunc(NEW.quantity)
 THEN RAISE EXCEPTION 'This stock unit requires whole quantities'; END IF;
 SELECT max(date) INTO latest FROM inventory_movement WHERE item_id=NEW.item_id;
 IF latest IS NOT NULL AND NEW.date<latest THEN RAISE EXCEPTION 'Stock chronology is locked'; END IF;
 IF NOT EXISTS(SELECT 1 FROM accounting_accountingperiod p JOIN accounting_fiscalyear y ON y.id=p.fiscal_year_id
   WHERE NEW.date BETWEEN p.start AND p.end AND NOT p.is_closed AND NOT y.is_closed)
 THEN RAISE EXCEPTION 'Stock period is closed'; END IF;
 SELECT COALESCE(sum(quantity),0),COALESCE(sum(base_value),0) INTO qty,value
 FROM inventory_movement WHERE item_id=NEW.item_id;
 IF qty+NEW.quantity<0 OR value+NEW.base_value<0 THEN RAISE EXCEPTION 'Negative stock/cost pool'; END IF;
 SELECT COALESCE(sum(quantity),0) INTO qty FROM inventory_movement
 WHERE item_id=NEW.item_id AND location_id=NEW.location_id;
 IF qty+NEW.quantity<0 THEN RAISE EXCEPTION 'Negative location stock'; END IF;
 IF NEW.quantity*NEW.base_value<0 THEN RAISE EXCEPTION 'Stock quantity/value direction mismatch'; END IF;
 IF NEW.kind IN ('transfer_in','transfer_out') THEN
  IF NEW.journal_id IS NOT NULL THEN RAISE EXCEPTION 'Transfers cannot post value twice'; END IF;
  IF NEW.kind='transfer_in' AND NOT EXISTS(SELECT 1 FROM inventory_movement m WHERE m.id=NEW.original_id
    AND m.kind='transfer_out' AND m.item_id=NEW.item_id AND m.source_id=NEW.source_id
    AND m.quantity=-NEW.quantity AND m.base_value=-NEW.base_value AND m.location_id<>NEW.location_id)
  THEN RAISE EXCEPTION 'Transfer must reference its matching outgoing leg'; END IF;
 ELSIF NEW.base_value<>0 THEN
  IF NEW.journal_id IS NULL OR NOT EXISTS(SELECT 1 FROM accounting_journalentry j
    WHERE j.id=NEW.journal_id AND j.status='posted' AND j.posting_date=NEW.date)
  THEN RAISE EXCEPTION 'Valued stock requires its posted source journal'; END IF;
  SELECT COALESCE(sum(l.base_debit-l.base_credit),0) INTO journal_value
  FROM accounting_journalline l JOIN accounting_account a ON a.id=l.account_id
  WHERE l.journal_id=NEW.journal_id AND a.control='inventory';
  IF journal_value<>NEW.base_value THEN RAISE EXCEPTION 'Stock must equal its source inventory posting'; END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER inventory_insert_guard BEFORE INSERT ON inventory_movement
FOR EACH ROW EXECUTE FUNCTION mateerp_stock_insert_guard();

CREATE FUNCTION mateerp_stock_reconciles() RETURNS trigger AS $$
DECLARE stock numeric; ledger numeric;
BEGIN
 IF TG_TABLE_NAME='accounting_journalentry' THEN
  IF NEW.status<>'posted' THEN RETURN NULL; END IF;
 END IF;
 SELECT COALESCE(sum(base_value),0) INTO stock FROM inventory_movement;
 SELECT COALESCE(sum(l.base_debit-l.base_credit),0) INTO ledger FROM accounting_journalline l
 JOIN accounting_journalentry j ON j.id=l.journal_id JOIN accounting_account a ON a.id=l.account_id
 WHERE j.status='posted' AND a.control='inventory';
 IF stock<>ledger THEN RAISE EXCEPTION 'Inventory source value must reconcile with GL'; END IF;
 IF EXISTS(SELECT 1 FROM inventory_movement o WHERE o.kind='transfer_out' AND NOT EXISTS(
   SELECT 1 FROM inventory_movement i WHERE i.original_id=o.id AND i.kind='transfer_in'))
 THEN RAISE EXCEPTION 'Stock transfers require both retained legs'; END IF;
 RETURN NULL;
END; $$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER inventory_balanced AFTER INSERT ON inventory_movement
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_stock_reconciles();
CREATE CONSTRAINT TRIGGER inventory_gl_balanced AFTER INSERT OR UPDATE ON accounting_journalentry
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_stock_reconciles();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0002_immutable_movements"),
        ("catalog", "0002_immutable_prices"),
        ("accounting", "0007_operational_controls"),
    ]
    operations = [migrations.RunSQL(SQL, """
    DROP TRIGGER inventory_insert_guard ON inventory_movement;
    DROP TRIGGER inventory_balanced ON inventory_movement;
    DROP TRIGGER inventory_gl_balanced ON accounting_journalentry;
    DROP FUNCTION mateerp_stock_insert_guard();
    DROP FUNCTION mateerp_stock_reconciles();
    """)]
