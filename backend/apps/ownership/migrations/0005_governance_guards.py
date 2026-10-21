from django.db import migrations


SQL = r"""
CREATE FUNCTION mateerp_ownership_governance_guard() RETURNS trigger AS $$
DECLARE a approvals_approvalrequest; required integer;
BEGIN
 PERFORM mateerp_financial_lock();
 IF OLD.snapshot<>'{}'::jsonb AND NEW.snapshot IS DISTINCT FROM OLD.snapshot THEN
  RAISE EXCEPTION 'Ownership preview and required parties are frozen' USING ERRCODE='23514';
 END IF;
 IF OLD.status IN ('rejected','cancelled') AND NEW.status<>OLD.status THEN
  RAISE EXCEPTION 'Declined proposals require a new proposal and authorization' USING ERRCODE='23514';
 END IF;
 IF NEW.status='confirmed' AND OLD.status<>'confirmed' THEN
  SELECT * INTO a FROM approvals_approvalrequest WHERE id=NEW.approval_id;
  required:=COALESCE((a.policy_snapshot->>'required_approvals')::integer,1);
  IF a.action<>'ownership.review' OR (a.payload->>'proposal_id')::bigint<>NEW.id OR
     a.payload->>'fingerprint'<>NEW.fingerprint OR
     (SELECT COUNT(*) FROM approvals_approvalvote v JOIN accounts_user u ON u.id=v.actor_id
      WHERE v.request_id=a.id AND v.actor_id<>a.requested_by_id AND u.is_active AND NOT u.must_change_password)<required THEN
   RAISE EXCEPTION 'Ownership confirmation needs its distinct independent quorum' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER ownership_governance_guard BEFORE UPDATE ON ownership_ownershipproposal FOR EACH ROW EXECUTE FUNCTION mateerp_ownership_governance_guard();

CREATE FUNCTION mateerp_ownership_consent_guard() RETURNS trigger AS $$
DECLARE p ownership_ownershipproposal; party company_financialparty;
BEGIN
 PERFORM mateerp_financial_lock();
 SELECT * INTO p FROM ownership_ownershipproposal WHERE id=NEW.proposal_id FOR UPDATE;
 SELECT * INTO party FROM company_financialparty WHERE id=NEW.party_id;
 IF p.status<>'draft' OR NEW.proposal_fingerprint<>p.fingerprint OR
  NOT (p.snapshot->'required_parties' @> to_jsonb(NEW.party_id)) THEN
  RAISE EXCEPTION 'Consent must authorize the frozen affected-party proposal' USING ERRCODE='23514';
 END IF;
 IF NEW.mode='authenticated' THEN
  IF party.user_id IS DISTINCT FROM NEW.actor_id THEN
   RAISE EXCEPTION 'Authenticated consent must be the linked shareholder' USING ERRCODE='23514';
  END IF;
 ELSIF NEW.mode='attestation' THEN
  IF party.user_id IS NOT NULL OR NEW.reference='' OR NOT EXISTS(
   SELECT 1 FROM ownership_ownershipevidence WHERE proposal_id=p.id AND party_id=party.id
  ) THEN RAISE EXCEPTION 'External attestation requires party-specific authorization evidence' USING ERRCODE='23514'; END IF;
 ELSE RAISE EXCEPTION 'Unknown ownership consent mode' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER ownership_consent_guard BEFORE INSERT ON ownership_ownershipconsent FOR EACH ROW EXECUTE FUNCTION mateerp_ownership_consent_guard();

CREATE FUNCTION mateerp_share_class_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF EXISTS(SELECT 1 FROM ownership_ownershipproposal WHERE share_class_id=OLD.id AND status='confirmed') THEN
  RAISE EXCEPTION 'Confirmed share-class rights and nominal values are historical' USING ERRCODE='23514';
 END IF;
 RETURN COALESCE(NEW,OLD);
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER share_class_guard BEFORE UPDATE OR DELETE ON ownership_shareclass FOR EACH ROW EXECUTE FUNCTION mateerp_share_class_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("ownership", "0004_alter_ownershipproposal_confirmed_at"), ("founders", "0007_funding_history_guards")]
    operations = [migrations.RunSQL(SQL)]
