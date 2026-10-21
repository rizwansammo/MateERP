from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('billing', '0006_dispatchrecall')]
    operations = [migrations.RunSQL('''
        CREATE TRIGGER dispatch_recall_immutable BEFORE UPDATE OR DELETE ON billing_dispatchrecall
        FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
        CREATE FUNCTION mateerp_dispatch_recall_guard() RETURNS trigger AS $$
        DECLARE d billing_dispatch%ROWTYPE; used numeric; m inventory_movement%ROWTYPE;
        BEGIN
          PERFORM mateerp_financial_lock();
          SELECT * INTO d FROM billing_dispatch WHERE id=NEW.dispatch_id;
          SELECT COALESCE(sum(quantity),0) INTO used FROM billing_controltransfer WHERE dispatch_id=d.id;
          SELECT used+COALESCE(sum(quantity),0) INTO used FROM billing_dispatchrecall WHERE dispatch_id=d.id;
          SELECT * INTO m FROM inventory_movement WHERE id=NEW.movement_id;
          IF used+NEW.quantity>d.quantity OR NEW.date<d.date OR m.kind<>'transfer_out'
            OR m.location_id<>d.transit_location_id OR m.quantity<>-NEW.quantity
          THEN RAISE EXCEPTION 'Recall must return only goods still owned in transit'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER dispatch_recall_source BEFORE INSERT ON billing_dispatchrecall
        FOR EACH ROW EXECUTE FUNCTION mateerp_dispatch_recall_guard();
    ''', '''
        DROP TRIGGER dispatch_recall_source ON billing_dispatchrecall;
        DROP TRIGGER dispatch_recall_immutable ON billing_dispatchrecall;
        DROP FUNCTION mateerp_dispatch_recall_guard();
    ''')]
