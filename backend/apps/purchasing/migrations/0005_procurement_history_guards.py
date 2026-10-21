from django.db import migrations

SQL = """
CREATE TRIGGER purchase_order_snapshot_immutable BEFORE UPDATE OR DELETE ON purchasing_purchaseordersnapshot
FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
CREATE TRIGGER goods_receipt_immutable BEFORE UPDATE OR DELETE ON purchasing_goodsreceipt
FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
CREATE OR REPLACE FUNCTION mateerp_po_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_TABLE_NAME='purchasing_purchaseorder' THEN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Retain purchase order history'; END IF;
  IF OLD.status NOT IN ('draft','rejected') AND
    ROW(NEW.number,NEW.vendor_id,NEW.date,NEW.currency,NEW.notes,NEW.prices_include_tax,NEW.revision,NEW.taxable,NEW.tax,NEW.total)
    IS DISTINCT FROM
    ROW(OLD.number,OLD.vendor_id,OLD.date,OLD.currency,OLD.notes,OLD.prices_include_tax,OLD.revision,OLD.taxable,OLD.tax,OLD.total)
  THEN RAISE EXCEPTION 'Approved purchase content is frozen'; END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM purchasing_purchaseorder WHERE id=COALESCE(NEW.order_id,OLD.order_id) AND status NOT IN ('draft','rejected'))
  THEN RAISE EXCEPTION 'Approved purchase lines are frozen'; END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER purchase_order_frozen BEFORE UPDATE OR DELETE ON purchasing_purchaseorder
FOR EACH ROW EXECUTE FUNCTION mateerp_po_guard();
CREATE TRIGGER purchase_order_lines_frozen BEFORE INSERT OR UPDATE OR DELETE ON purchasing_purchaseorderline
FOR EACH ROW EXECUTE FUNCTION mateerp_po_guard();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0004_purchaseorder_purchaseorderline_goodsreceipt_and_more"),
        ("inventory", "0002_immutable_movements"),
        ("accounting", "0007_operational_controls"),
    ]
    operations = [migrations.RunSQL(SQL, """
    DROP TRIGGER purchase_order_snapshot_immutable ON purchasing_purchaseordersnapshot;
    DROP TRIGGER goods_receipt_immutable ON purchasing_goodsreceipt;
    DROP TRIGGER purchase_order_frozen ON purchasing_purchaseorder;
    DROP TRIGGER purchase_order_lines_frozen ON purchasing_purchaseorderline;
    DROP FUNCTION mateerp_po_guard();
    """)]
