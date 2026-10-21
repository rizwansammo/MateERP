from django.db import migrations


IMMUTABLE = ['assetestimate','depreciationcharge','assetdisposal','assetevidence']
RECON_TABLES = ['assets_asset','assets_depreciationcharge','assets_assetdisposal','accounting_journalentry']


class Migration(migrations.Migration):
    dependencies = [('assets','0001_initial'), ('accounting','0007_operational_controls')]
    operations = [migrations.RunSQL('''
    CREATE FUNCTION mateerp_asset_guard() RETURNS trigger AS $$
    DECLARE claimed numeric; source accounting_journalline%ROWTYPE;
    BEGIN
      PERFORM mateerp_financial_lock();
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Retain asset history'; END IF;
      IF TG_OP='UPDATE' THEN
        IF ROW(NEW.tag,NEW.source_line_id,NEW.source_snapshot,NEW.acquisition_date,NEW.recognition_date,NEW.in_service_date,NEW.cost,NEW.journal_id,NEW.depreciation_account_id,NEW.created_by_id,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.tag,OLD.source_line_id,OLD.source_snapshot,OLD.acquisition_date,OLD.recognition_date,OLD.in_service_date,OLD.cost,OLD.journal_id,OLD.depreciation_account_id,OLD.created_by_id,OLD.created_at)
        THEN RAISE EXCEPTION 'Capitalized asset financial identity is immutable'; END IF;
        RETURN NEW;
      END IF;
      SELECT * INTO source FROM accounting_journalline WHERE id=NEW.source_line_id;
      SELECT COALESCE(sum(cost),0) INTO claimed FROM assets_asset WHERE source_line_id=NEW.source_line_id;
      IF NOT EXISTS(SELECT 1 FROM accounting_journalentry j JOIN accounting_account a ON a.id=source.account_id
       WHERE j.id=source.journal_id AND j.status='posted' AND j.source_type IN ('vendor_bill','expense','founder_transaction')
       AND a.control='' AND a.account_type IN ('asset','expense'))
       OR claimed+NEW.cost>source.base_debit-source.base_credit
      THEN RAISE EXCEPTION 'Asset acquisition must be a real, unclaimed source debit'; END IF;
      IF NOT EXISTS(SELECT 1 FROM accounting_journalentry WHERE id=NEW.journal_id AND status='posted' AND source_type='asset_event')
      THEN RAISE EXCEPTION 'Capitalization requires its source journal'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER asset_source_guard BEFORE INSERT OR UPDATE OR DELETE ON assets_asset
    FOR EACH ROW EXECUTE FUNCTION mateerp_asset_guard();
    CREATE FUNCTION mateerp_asset_action_guard() RETURNS trigger AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Retain asset action history'; END IF;
      IF OLD.status<>'pending' OR ROW(NEW.operation,NEW.key,NEW.fingerprint,NEW.payload,NEW.created_by_id,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.operation,OLD.key,OLD.fingerprint,OLD.payload,OLD.created_by_id,OLD.created_at)
      THEN RAISE EXCEPTION 'Asset action identity is frozen'; END IF;
      IF NEW.status NOT IN ('pending','done','rejected') THEN RAISE EXCEPTION 'Invalid asset action state'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER asset_action_frozen BEFORE UPDATE OR DELETE ON assets_assetaction
    FOR EACH ROW EXECUTE FUNCTION mateerp_asset_action_guard();
    CREATE FUNCTION mateerp_assets_reconcile() RETURNS trigger AS $$
    DECLARE cost numeric; removed numeric; dep numeric; released numeric; glcost numeric; gldep numeric;
    BEGIN
      SELECT COALESCE(sum(a.cost),0) INTO cost FROM assets_asset a;
      SELECT COALESCE(sum(a.cost),0),COALESCE(sum(d.accumulated),0) INTO removed,released
      FROM assets_assetdisposal d JOIN assets_asset a ON a.id=d.asset_id;
      SELECT COALESCE(sum(amount),0) INTO dep FROM assets_depreciationcharge;
      SELECT COALESCE(sum(l.base_debit-l.base_credit) FILTER(WHERE a.control='fixed_assets'),0),
        COALESCE(sum(l.base_credit-l.base_debit) FILTER(WHERE a.control='accumulated_depreciation'),0)
      INTO glcost,gldep FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id
      JOIN accounting_account a ON a.id=l.account_id WHERE j.status='posted';
      IF cost-removed<>glcost OR dep-released<>gldep THEN RAISE EXCEPTION 'Asset register and depreciation must reconcile to GL'; END IF;
      IF EXISTS(SELECT 1 FROM assets_asset a JOIN accounting_journalline l ON l.id=a.source_line_id
        JOIN accounting_journalentry j ON j.reversal_of_id=l.journal_id AND j.status='posted')
      THEN RAISE EXCEPTION 'Capitalized acquisition cannot be reversed independently'; END IF;
      RETURN NULL;
    END; $$ LANGUAGE plpgsql;
    ''' + '\n'.join(f'CREATE TRIGGER {t}_immutable BEFORE UPDATE OR DELETE ON assets_{t} FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();' for t in IMMUTABLE)
    + '\n' + '\n'.join(f'CREATE CONSTRAINT TRIGGER asset_reconcile_{t} AFTER INSERT OR UPDATE OR DELETE ON {t} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_assets_reconcile();' for t in RECON_TABLES),
    '\n'.join(f'DROP TRIGGER {t}_immutable ON assets_{t};' for t in IMMUTABLE)+'\n'+
    '\n'.join(f'DROP TRIGGER asset_reconcile_{t} ON {t};' for t in RECON_TABLES)+'''
    DROP TRIGGER asset_source_guard ON assets_asset;
    DROP TRIGGER asset_action_frozen ON assets_assetaction;
    DROP FUNCTION mateerp_asset_guard(); DROP FUNCTION mateerp_asset_action_guard(); DROP FUNCTION mateerp_assets_reconcile();
    ''')]
