from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION mateerp_count_guard() RETURNS trigger AS $$
    BEGIN
      PERFORM mateerp_financial_lock();
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Retain count history'; END IF;
      IF OLD.status<>'pending' OR NEW.payload<>OLD.payload OR NEW.basis<>OLD.basis
       OR NEW.key<>OLD.key OR NEW.fingerprint<>OLD.fingerprint
       OR NEW.created_by_id<>OLD.created_by_id OR NEW.created_at<>OLD.created_at
      THEN RAISE EXCEPTION 'Count financial identity is frozen'; END IF;
      IF NEW.status='posted' AND NOT EXISTS(SELECT 1 FROM inventory_movement m WHERE m.id=NEW.movement_id
       AND m.kind=CASE WHEN NEW.payload->>'kind'='valuation' THEN 'price_adjustment' ELSE 'count' END AND m.source_key=NEW.key AND m.fingerprint=NEW.fingerprint)
      THEN RAISE EXCEPTION 'Posted count requires its exact movement'; END IF;
      IF NEW.status NOT IN ('pending','posted','rejected') THEN RAISE EXCEPTION 'Invalid count state'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
"""
REVERSE = """
CREATE OR REPLACE FUNCTION mateerp_count_guard() RETURNS trigger AS $$
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
"""

class Migration(migrations.Migration):
    dependencies = [("inventory", "0006_count_integrity")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
