from django.db import migrations

SQL = r"""
CREATE FUNCTION mateerp_ownership_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Ownership history is retained' USING ERRCODE='23514'; END IF;
 IF OLD.status='confirmed' AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN RAISE EXCEPTION 'Confirmed ownership is immutable' USING ERRCODE='23514'; END IF;
 IF (to_jsonb(NEW)-ARRAY['status','approval_id','confirmed_by_id','confirmed_at','snapshot']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','approval_id','confirmed_by_id','confirmed_at','snapshot']) THEN RAISE EXCEPTION 'Ownership proposal content is frozen' USING ERRCODE='23514'; END IF;
 IF OLD.status<>'draft' AND NEW.snapshot IS DISTINCT FROM OLD.snapshot THEN RAISE EXCEPTION 'Reviewed ownership snapshot is frozen' USING ERRCODE='23514'; END IF;
 IF NEW.status='confirmed' AND OLD.status<>'confirmed' THEN
  IF NEW.approval_id IS NULL OR NOT EXISTS(SELECT 1 FROM approvals_approvalrequest WHERE id=NEW.approval_id AND status='approved') OR NEW.legal_reference='' OR NOT EXISTS(SELECT 1 FROM ownership_ownershipevidence WHERE proposal_id=NEW.id) THEN RAISE EXCEPTION 'Ownership confirmation needs approval and evidence' USING ERRCODE='23514'; END IF;
  IF EXISTS(SELECT 1 FROM jsonb_array_elements_text(NEW.snapshot->'required_parties') r WHERE NOT EXISTS(SELECT 1 FROM ownership_ownershipconsent c WHERE c.proposal_id=NEW.id AND c.party_id=r.value::bigint AND c.proposal_fingerprint=NEW.fingerprint)) THEN RAISE EXCEPTION 'Missing affected shareholder authorization' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER ownership_guard BEFORE UPDATE OR DELETE ON ownership_ownershipproposal FOR EACH ROW EXECUTE FUNCTION mateerp_ownership_guard();

CREATE FUNCTION mateerp_ownership_line_guard() RETURNS trigger AS $$
DECLARE p bigint;
BEGIN
 PERFORM mateerp_financial_lock();
 p:=COALESCE(NEW.proposal_id,OLD.proposal_id);
 IF EXISTS(SELECT 1 FROM ownership_ownershipproposal WHERE id=p AND status<>'draft') OR EXISTS(SELECT 1 FROM ownership_ownershipconsent WHERE proposal_id=p) THEN RAISE EXCEPTION 'Authorized ownership lines are frozen' USING ERRCODE='23514'; END IF;
 RETURN COALESCE(NEW,OLD);
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER ownership_line_guard BEFORE INSERT OR UPDATE OR DELETE ON ownership_ownershipline FOR EACH ROW EXECUTE FUNCTION mateerp_ownership_line_guard();

CREATE FUNCTION mateerp_ownership_balance_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF EXISTS(WITH movements AS (
   SELECT p.share_class_id,p.effective_date,p.id,l.recipient_id AS party,l.units::numeric AS units FROM ownership_ownershipline l JOIN ownership_ownershipproposal p ON p.id=l.proposal_id WHERE p.status='confirmed'
   UNION ALL SELECT p.share_class_id,p.effective_date,p.id,l.transferor_id,-l.units::numeric FROM ownership_ownershipline l JOIN ownership_ownershipproposal p ON p.id=l.proposal_id WHERE p.status='confirmed' AND p.kind='transfer'
 ), grouped AS (SELECT share_class_id,effective_date,id,party,SUM(units) units FROM movements GROUP BY share_class_id,effective_date,id,party), balances AS (
 SELECT SUM(units) OVER(PARTITION BY share_class_id,party ORDER BY effective_date,id) balance FROM grouped)
 SELECT 1 FROM balances WHERE balance<0) THEN RAISE EXCEPTION 'Confirmed share register cannot oversell' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END; $$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER ownership_balance_guard AFTER INSERT OR UPDATE ON ownership_ownershipproposal DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_ownership_balance_guard();
CREATE TRIGGER ownership_consent_append_only BEFORE UPDATE OR DELETE ON ownership_ownershipconsent FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
CREATE TRIGGER ownership_evidence_append_only BEFORE UPDATE OR DELETE ON ownership_ownershipevidence FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
CREATE TRIGGER approval_vote_append_only BEFORE UPDATE OR DELETE ON approvals_approvalvote FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
"""


class Migration(migrations.Migration):
    dependencies = [("ownership", "0001_initial"), ("accounting", "0006_founder_controls")]
    operations = [migrations.RunSQL(SQL)]
