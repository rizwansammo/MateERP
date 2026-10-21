from django.db import migrations

IMMUTABLE = ["founderobligation", "obligationallocation", "foundervendorallocation", "sharedexpense", "personalobligation", "personalallocation", "personalconfirmation", "recoveryresolution", "fundingplan", "founderevidence"]

SQL = r"""
CREATE FUNCTION mateerp_founder_transaction_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Founder transaction history is retained' USING ERRCODE='23514'; END IF;
 IF OLD.status IN ('posted','reversed') AND
  (to_jsonb(NEW)-ARRAY['status','reversal_journal_id']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','reversal_journal_id']) THEN
   RAISE EXCEPTION 'Posted founder sources are immutable' USING ERRCODE='23514';
 END IF;
 IF OLD.status='reversed' AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
   RAISE EXCEPTION 'Founder reversal is final' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER founder_transaction_guard BEFORE UPDATE OR DELETE ON founders_corporatetransaction FOR EACH ROW EXECUTE FUNCTION mateerp_founder_transaction_guard();

CREATE FUNCTION mateerp_founder_allocation_guard() RETURNS trigger AS $$
DECLARE o founders_founderobligation; t founders_corporatetransaction; used numeric; used_base numeric;
BEGIN
 PERFORM mateerp_financial_lock();
 SELECT * INTO o FROM founders_founderobligation WHERE id=NEW.obligation_id FOR UPDATE;
 SELECT * INTO t FROM founders_corporatetransaction WHERE id=NEW.transaction_id;
 SELECT COALESCE(SUM(a.amount),0), COALESCE(SUM(a.base_amount),0) INTO used,used_base FROM founders_obligationallocation a JOIN founders_corporatetransaction tx ON tx.id=a.transaction_id WHERE a.obligation_id=o.id AND tx.status='posted';
 IF t.status<>'posted' OR t.party_id<>o.party_id OR t.currency<>o.currency OR used+NEW.amount>o.amount OR used_base+NEW.base_amount>o.base_amount THEN
   RAISE EXCEPTION 'Invalid or excessive founder liability allocation' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER founder_allocation_guard BEFORE INSERT ON founders_obligationallocation FOR EACH ROW EXECUTE FUNCTION mateerp_founder_allocation_guard();

CREATE FUNCTION mateerp_personal_transfer_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Personal transfer evidence is retained' USING ERRCODE='23514'; END IF;
 IF (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') OR (OLD.status='confirmed' AND NEW.status<>'confirmed') THEN
   RAISE EXCEPTION 'Personal transfer content is immutable' USING ERRCODE='23514';
 END IF;
 IF NEW.status='confirmed' AND OLD.status<>'confirmed' THEN
  IF (SELECT COUNT(*) FROM founders_personalconfirmation WHERE settlement_id=NEW.id)<>2 OR (SELECT SUM(amount) FROM founders_personalallocation WHERE settlement_id=NEW.id) IS DISTINCT FROM NEW.amount THEN
    RAISE EXCEPTION 'Personal transfer needs both confirmations and exact allocations' USING ERRCODE='23514';
  END IF;
  IF NOT NEW.is_return AND EXISTS(SELECT 1 FROM founders_personalallocation a JOIN founders_personalobligation o ON o.id=a.obligation_id WHERE a.settlement_id=NEW.id AND
    (SELECT COALESCE(SUM(CASE WHEN s.is_return THEN -pa.amount ELSE pa.amount END),0) FROM founders_personalallocation pa JOIN founders_personalsettlement s ON s.id=pa.settlement_id WHERE pa.obligation_id=o.id AND (s.status='confirmed' OR s.id=NEW.id))>o.amount) THEN
    RAISE EXCEPTION 'Personal obligation is over-settled' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER personal_transfer_guard BEFORE UPDATE OR DELETE ON founders_personalsettlement FOR EACH ROW EXECUTE FUNCTION mateerp_personal_transfer_guard();

CREATE FUNCTION mateerp_sharing_policy_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Sharing policy history is retained' USING ERRCODE='23514'; END IF;
 IF OLD.status='active' AND (to_jsonb(NEW)-'effective_until') IS DISTINCT FROM (to_jsonb(OLD)-'effective_until') THEN
   RAISE EXCEPTION 'Active sharing policy content is immutable' USING ERRCODE='23514';
 END IF;
 IF NEW.status='active' AND EXISTS(SELECT 1 FROM founders_sharingpolicy p WHERE p.id<>NEW.id AND p.status='active' AND p.category_id IS NOT DISTINCT FROM NEW.category_id AND daterange(p.effective_from,p.effective_until,'[]') && daterange(NEW.effective_from,NEW.effective_until,'[]')) THEN
   RAISE EXCEPTION 'Sharing policy effective dates overlap' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER sharing_policy_guard BEFORE UPDATE OR DELETE ON founders_sharingpolicy FOR EACH ROW EXECUTE FUNCTION mateerp_sharing_policy_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("founders", "0001_initial"), ("accounting", "0006_founder_controls"), ("purchasing", "0003_remove_expense_expense_mode_consistent_and_more")]
    operations = [migrations.RunSQL(SQL)] + [migrations.RunSQL(f"CREATE TRIGGER {name}_append_only BEFORE UPDATE OR DELETE ON founders_{name} FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();") for name in IMMUTABLE]
