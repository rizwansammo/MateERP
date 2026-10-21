from django.db import migrations


SQL = r"""
CREATE FUNCTION mateerp_founder_state_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF OLD.status='posted' AND NEW.status NOT IN ('posted','reversed') THEN
  RAISE EXCEPTION 'Posted founder transactions only allow traceable reversal' USING ERRCODE='23514';
 END IF;
 IF NEW.status='reversed' AND NEW.reversal_journal_id IS NULL THEN
  RAISE EXCEPTION 'Founder reversal requires its journal' USING ERRCODE='23514';
 END IF;
 IF (to_jsonb(NEW)-ARRAY['status','approval_id','verified_by_id','journal_id','reversal_journal_id','base_amount','snapshot'])
  IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','approval_id','verified_by_id','journal_id','reversal_journal_id','base_amount','snapshot']) THEN
  RAISE EXCEPTION 'Founder source identity is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER founder_state_guard BEFORE UPDATE ON founders_corporatetransaction FOR EACH ROW EXECUTE FUNCTION mateerp_founder_state_guard();

CREATE FUNCTION mateerp_founder_personal_allocation_insert_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF NOT EXISTS(SELECT 1 FROM founders_personalsettlement WHERE id=NEW.settlement_id AND status='recorded') THEN
  RAISE EXCEPTION 'Personal allocations must precede confirmation' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER personal_allocation_insert_guard BEFORE INSERT ON founders_personalallocation FOR EACH ROW EXECUTE FUNCTION mateerp_founder_personal_allocation_insert_guard();

CREATE FUNCTION mateerp_funding_consumption_guard() RETURNS trigger AS $$
DECLARE d founders_fundingdesignation; e purchasing_expense; original founders_fundingconsumption; used numeric; covered numeric;
BEGIN
 PERFORM mateerp_financial_lock();
 SELECT * INTO d FROM founders_fundingdesignation WHERE id=NEW.designation_id FOR UPDATE;
 SELECT * INTO e FROM purchasing_expense WHERE id=NEW.expense_id;
 IF NEW.reverses_id IS NOT NULL THEN
  SELECT * INTO original FROM founders_fundingconsumption WHERE id=NEW.reverses_id;
  IF original.reverses_id IS NOT NULL OR NEW.reason='' OR
   (NEW.designation_id,NEW.expense_id,NEW.amount) IS DISTINCT FROM (original.designation_id,original.expense_id,original.amount) THEN
   RAISE EXCEPTION 'Funding releases must exactly reverse their original allocation' USING ERRCODE='23514';
  END IF;
 ELSE
  IF e.status<>'paid' OR e.payment_mode<>'paid' OR NOT EXISTS(
   SELECT 1 FROM founders_corporatetransaction t WHERE t.id=d.receipt_id AND t.status='posted' AND t.bank_id=e.bank_account_id AND t.currency=e.currency
  ) THEN RAISE EXCEPTION 'Funding consumption requires the actual company payment' USING ERRCODE='23514'; END IF;
  SELECT COALESCE(SUM(c.amount),0) INTO used FROM founders_fundingconsumption c WHERE c.designation_id=d.id AND c.reverses_id IS NULL AND NOT EXISTS(SELECT 1 FROM founders_fundingconsumption r WHERE r.reverses_id=c.id);
  SELECT COALESCE(SUM(c.amount),0) INTO covered FROM founders_fundingconsumption c WHERE c.expense_id=e.id AND c.reverses_id IS NULL AND NOT EXISTS(SELECT 1 FROM founders_fundingconsumption r WHERE r.reverses_id=c.id);
  covered:=covered+(SELECT COALESCE(SUM(amount),0) FROM founders_companyfundingcoverage WHERE expense_id=e.id AND status='consumed');
  IF used+NEW.amount>d.amount OR covered+NEW.amount>e.total THEN
   RAISE EXCEPTION 'Funding cannot exceed the designation or actual expense' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER funding_consumption_guard BEFORE INSERT ON founders_fundingconsumption FOR EACH ROW EXECUTE FUNCTION mateerp_funding_consumption_guard();
CREATE TRIGGER funding_consumption_append_only BEFORE UPDATE OR DELETE ON founders_fundingconsumption FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
CREATE TRIGGER reserve_transfer_append_only BEFORE UPDATE OR DELETE ON founders_reservedesignationtransfer FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();

CREATE FUNCTION mateerp_phase5_approval_guard() RETURNS trigger AS $$
BEGIN
 IF OLD.action IN ('founder.post','founder.policy','ownership.review') AND
  (NEW.action,NEW.payload,NEW.policy_snapshot,NEW.requested_by_id,NEW.subject_key) IS DISTINCT FROM
  (OLD.action,OLD.payload,OLD.policy_snapshot,OLD.requested_by_id,OLD.subject_key) THEN
  RAISE EXCEPTION 'Reviewed founder and ownership approval identity is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER phase5_approval_guard BEFORE UPDATE ON approvals_approvalrequest FOR EACH ROW EXECUTE FUNCTION mateerp_phase5_approval_guard();
"""


def preserve_legacy_consumption(apps, schema_editor):
    Designation = apps.get_model("founders", "FundingDesignation")
    Consumption = apps.get_model("founders", "FundingConsumption")
    for obj in Designation.objects.filter(consumed_by__isnull=False):
        Consumption.objects.get_or_create(
            designation_id=obj.pk,
            expense_id=obj.consumed_by_id,
            defaults={"amount": obj.amount, "created_by_id": obj.created_by_id},
        )


class Migration(migrations.Migration):
    dependencies = [("founders", "0006_fundingconsumption_and_more")]
    operations = [migrations.RunPython(preserve_legacy_consumption, migrations.RunPython.noop), migrations.RunSQL(SQL)]
