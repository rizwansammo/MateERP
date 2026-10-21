from django.db import migrations

TABLES = ("fulfillmentpolicy", "dispatch", "controltransfer", "invoicerecognitionbinding",
          "deferredcreditallocation", "customerreturn")
IMMUTABLE = "\n".join(
    f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON billing_{table} "
    "FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();" for table in TABLES
)
SQL = """
CREATE FUNCTION mateerp_control_transfer_guard() RETURNS trigger AS $$
DECLARE qty numeric; p billing_fulfillmentpolicy%ROWTYPE; m inventory_movement%ROWTYPE;
        n numeric; b numeric; q numeric;
BEGIN
 PERFORM mateerp_financial_lock();
 SELECT * INTO p FROM billing_fulfillmentpolicy WHERE id=NEW.policy_id;
 SELECT COALESCE(sum(quantity),0) INTO qty FROM billing_controltransfer WHERE policy_id=p.id;
 IF qty+NEW.quantity>(p.snapshot->>'quantity')::numeric THEN RAISE EXCEPTION 'Control quantity exceeds contract'; END IF;
 SELECT * INTO m FROM inventory_movement WHERE id=NEW.movement_id;
 IF NOT FOUND OR m.item_id<>(p.snapshot->>'item_id')::bigint OR m.kind<>'issue'
   OR m.quantity<>-NEW.quantity OR m.base_value<>-NEW.base_cogs
   OR m.journal_id IS DISTINCT FROM NEW.journal_id
 THEN RAISE EXCEPTION 'Control requires its exact stock/cost source'; END IF;
 IF (NEW.base_revenue<>0 OR NEW.base_cogs<>0) AND NOT EXISTS(
   SELECT 1 FROM accounting_journalentry WHERE id=NEW.journal_id AND status='posted'
     AND source_type='fulfillment_control' AND source_id=NEW.id::text)
 THEN RAISE EXCEPTION 'Control requires its source-owned journal'; END IF;
 SELECT COALESCE(sum((v->>'native')::numeric),0),COALESCE(sum((v->>'base')::numeric),0),
        COALESCE(sum((v->>'quantity')::numeric),0) INTO n,b,q
 FROM jsonb_array_elements(NEW.deferred_snapshot) v;
 IF NEW.net_native<>n+NEW.unbilled_native OR NEW.base_revenue<>b+NEW.unbilled_base
 THEN RAISE EXCEPTION 'Recognition snapshots must equal source totals'; END IF;
 IF p.trigger='control_transfer' AND NEW.quantity<>q+NEW.unbilled_quantity
 THEN RAISE EXCEPTION 'Every controlled unit requires one recognition allocation'; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER control_transfer_source BEFORE INSERT ON billing_controltransfer
FOR EACH ROW EXECUTE FUNCTION mateerp_control_transfer_guard();

CREATE FUNCTION mateerp_recognition_binding_guard() RETURNS trigger AS $$
DECLARE l billing_invoiceline%ROWTYPE; p billing_fulfillmentpolicy%ROWTYPE;
BEGIN
 PERFORM mateerp_financial_lock();
 SELECT * INTO l FROM billing_invoiceline WHERE id=NEW.invoice_line_id;
 SELECT * INTO p FROM billing_fulfillmentpolicy WHERE id=NEW.policy_id;
 IF NEW.unbilled_quantity+NEW.deferred_quantity<>l.quantity OR
    NEW.unbilled_native+NEW.deferred_native<>l.taxable OR l.sales_order_line_id<>p.order_line_id
 THEN RAISE EXCEPTION 'Invoice binding must allocate the exact contract line'; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER invoice_recognition_source BEFORE INSERT ON billing_invoicerecognitionbinding
FOR EACH ROW EXECUTE FUNCTION mateerp_recognition_binding_guard();

CREATE FUNCTION mateerp_recognition_reconciles() RETURNS trigger AS $$
DECLARE u numeric; d numeric; used numeric; gu numeric; gd numeric;
BEGIN
 SELECT COALESCE(sum(unbilled_base),0) INTO u FROM billing_controltransfer;
 SELECT COALESCE(sum(b.unbilled_base),0),COALESCE(sum(b.deferred_base),0) INTO used,d
 FROM billing_invoicerecognitionbinding b JOIN billing_invoiceline l ON l.id=b.invoice_line_id
 JOIN billing_invoice i ON i.id=l.invoice_id WHERE i.status IN ('issued','partially_paid','paid','credited');
 u:=u-used;
 SELECT COALESCE(sum((v->>'base')::numeric),0) INTO used FROM billing_controltransfer t,
 jsonb_array_elements(t.deferred_snapshot) v;
 d:=d-used;
 SELECT COALESCE(sum(a.base),0) INTO used FROM billing_deferredcreditallocation a
 JOIN billing_creditnoteline l ON l.id=a.credit_line_id JOIN billing_creditnote n ON n.id=l.credit_note_id
 WHERE n.status='issued';
 d:=d-used;
 SELECT COALESCE(sum(l.base_debit-l.base_credit) FILTER(WHERE a.control='unbilled_revenue'),0),
        COALESCE(sum(l.base_credit-l.base_debit) FILTER(WHERE a.control='deferred_revenue'),0)
 INTO gu,gd FROM accounting_journalline l JOIN accounting_account a ON a.id=l.account_id
 JOIN accounting_journalentry j ON j.id=l.journal_id WHERE j.status='posted';
 IF u<0 OR d<0 OR u<>gu OR d<>gd THEN RAISE EXCEPTION 'Recognition sources must reconcile to unbilled/deferred GL'; END IF;
 RETURN NULL;
END; $$ LANGUAGE plpgsql;
"""
RECON_TABLES = ("billing_controltransfer", "billing_invoicerecognitionbinding",
                "billing_deferredcreditallocation", "billing_invoice", "billing_creditnote",
                "accounting_journalentry")
RECON = "\n".join(
    f"CREATE CONSTRAINT TRIGGER recognition_reconcile_{table} AFTER INSERT OR UPDATE ON {table} "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_recognition_reconciles();"
    for table in RECON_TABLES
)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0004_fulfillmentpolicy_dispatch_controltransfer_and_more"),
        ("inventory", "0003_stock_integrity"),
    ]
    operations = [migrations.RunSQL(IMMUTABLE + SQL + RECON,
        "\n".join(f"DROP TRIGGER {table}_immutable ON billing_{table};" for table in TABLES)
        + "\n" + "\n".join(f"DROP TRIGGER recognition_reconcile_{t} ON {t};" for t in RECON_TABLES)
        + """
        DROP TRIGGER control_transfer_source ON billing_controltransfer;
        DROP TRIGGER invoice_recognition_source ON billing_invoicerecognitionbinding;
        DROP FUNCTION mateerp_control_transfer_guard();
        DROP FUNCTION mateerp_recognition_binding_guard();
        DROP FUNCTION mateerp_recognition_reconciles();
        """,
    )]
