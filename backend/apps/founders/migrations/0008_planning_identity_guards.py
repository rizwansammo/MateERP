from django.db import migrations


SQL = r"""
CREATE FUNCTION mateerp_funding_designation_guard() RETURNS trigger AS $$
DECLARE t founders_corporatetransaction;
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Funding allocation history is retained' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' THEN
  IF (to_jsonb(NEW)-'reserve_id') IS DISTINCT FROM (to_jsonb(OLD)-'reserve_id') OR NOT EXISTS(
   SELECT 1 FROM founders_reservedesignationtransfer WHERE designation_id=OLD.id AND previous_reserve_id=OLD.reserve_id AND new_reserve_id=NEW.reserve_id
  ) THEN RAISE EXCEPTION 'Funding allocation changes require an explicit retained-funds transfer' USING ERRCODE='23514'; END IF;
 ELSE
  SELECT * INTO t FROM founders_corporatetransaction WHERE id=NEW.receipt_id FOR UPDATE;
  IF t.kind<>'receipt' OR t.status<>'posted' OR NEW.amount+
   (SELECT COALESCE(SUM(amount),0) FROM founders_fundingdesignation WHERE receipt_id=t.id)>t.amount THEN
   RAISE EXCEPTION 'Funding designations require sufficient verified receipt funds' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER funding_designation_guard BEFORE INSERT OR UPDATE OR DELETE ON founders_fundingdesignation FOR EACH ROW EXECUTE FUNCTION mateerp_funding_designation_guard();

CREATE FUNCTION mateerp_company_coverage_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Company funding history is retained' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.status<>'active' OR NEW.expense_id IS NOT NULL OR NOT EXISTS(SELECT 1 FROM founders_fundingplan WHERE id=NEW.plan_id AND mode='partial') THEN
   RAISE EXCEPTION 'Company coverage must start as an explicit partial-plan allocation' USING ERRCODE='23514';
  END IF;
 ELSE
  IF (to_jsonb(NEW)-ARRAY['status','expense_id']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','expense_id']) OR
   OLD.status='released' OR (OLD.status='consumed' AND (NEW.status<>'released' OR NEW.expense_id IS DISTINCT FROM OLD.expense_id)) OR
   (OLD.status='active' AND NEW.status NOT IN ('consumed','released')) THEN
   RAISE EXCEPTION 'Company funding allocations cannot be rewritten' USING ERRCODE='23514';
  END IF;
  IF NEW.status='consumed' AND NOT EXISTS(SELECT 1 FROM purchasing_expense e WHERE e.id=NEW.expense_id AND e.status='paid' AND e.payment_mode='paid' AND e.bank_account_id=NEW.bank_id) THEN
   RAISE EXCEPTION 'Company coverage requires the actual posted payment' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER company_coverage_guard BEFORE INSERT OR UPDATE OR DELETE ON founders_companyfundingcoverage FOR EACH ROW EXECUTE FUNCTION mateerp_company_coverage_guard();

CREATE FUNCTION mateerp_annual_reserve_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Annual reserve history is retained' USING ERRCODE='23514'; END IF;
 IF (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') OR OLD.status<>'active' OR NEW.status<>'superseded' THEN
  RAISE EXCEPTION 'Reserve changes require a new documented revision' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER annual_reserve_guard BEFORE UPDATE OR DELETE ON founders_annualreserve FOR EACH ROW EXECUTE FUNCTION mateerp_annual_reserve_guard();
CREATE FUNCTION mateerp_funding_pledge_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Funding request history is retained' USING ERRCODE='23514'; END IF;
 IF (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') OR OLD.status='cancelled' OR
  NEW.status NOT IN ('promised','cancelled') OR (OLD.status='promised' AND NEW.status<>'cancelled') THEN
  RAISE EXCEPTION 'Funding request identity is frozen and status only advances' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER funding_pledge_guard BEFORE UPDATE OR DELETE ON founders_fundingpledge FOR EACH ROW EXECUTE FUNCTION mateerp_funding_pledge_guard();
CREATE TRIGGER founder_loan_append_only BEFORE UPDATE OR DELETE ON founders_founderloan FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
"""


class Migration(migrations.Migration):
    dependencies = [("founders", "0007_funding_history_guards")]
    operations = [migrations.RunSQL(SQL)]
