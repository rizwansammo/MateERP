from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('inventory', '0005_stockcount')]
    operations = [migrations.RunSQL('''
    CREATE FUNCTION mateerp_count_guard() RETURNS trigger AS $$
    BEGIN
      PERFORM mateerp_financial_lock();
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Retain count history'; END IF;
      IF OLD.status<>'pending' OR NEW.payload<>OLD.payload OR NEW.basis<>OLD.basis
       OR NEW.key<>OLD.key OR NEW.fingerprint<>OLD.fingerprint
       OR NEW.created_by_id<>OLD.created_by_id OR NEW.created_at<>OLD.created_at
      THEN RAISE EXCEPTION 'Count financial identity is frozen'; END IF;
      IF NEW.status='posted' AND NOT EXISTS(SELECT 1 FROM inventory_movement m WHERE m.id=NEW.movement_id
       AND m.kind='count' AND m.source_key=NEW.key AND m.fingerprint=NEW.fingerprint)
      THEN RAISE EXCEPTION 'Posted count requires its exact movement'; END IF;
      IF NEW.status NOT IN ('pending','posted','rejected') THEN RAISE EXCEPTION 'Invalid count state'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER stock_count_guard BEFORE UPDATE OR DELETE ON inventory_stockcount
    FOR EACH ROW EXECUTE FUNCTION mateerp_count_guard();
    ''', '''DROP TRIGGER stock_count_guard ON inventory_stockcount; DROP FUNCTION mateerp_count_guard();''')]
