"""Ledger invariants are checked independently of the Django write path."""
from django.db import migrations

SQL = r"""
CREATE FUNCTION mateerp_financial_lock() RETURNS void AS $$
BEGIN
  PERFORM id FROM company_companyprofile WHERE id=1 FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Company profile required' USING ERRCODE='23514'; END IF;
END; $$ LANGUAGE plpgsql;

CREATE FUNCTION mateerp_minor(c text) RETURNS integer AS $$
BEGIN
  IF c IN ('JPY','KRW') THEN RETURN 0; END IF;
  IF c IN ('BDT','USD','EUR','GBP','SGD','INR','AED','SAR','MYR','AUD','CAD','CHF','CNY','HKD','PKR','LKR','NPR','THB','NZD','SEK') THEN RETURN 2; END IF;
  RAISE EXCEPTION 'Unsupported currency %',c USING ERRCODE='23514';
END; $$ LANGUAGE plpgsql IMMUTABLE;

ALTER TABLE accounting_fiscalyear ADD CONSTRAINT fiscal_year_no_overlap EXCLUDE USING gist (daterange(start,"end",'[]') WITH &&);
ALTER TABLE accounting_accountingperiod ADD CONSTRAINT period_no_overlap EXCLUDE USING gist (daterange(start,"end",'[]') WITH &&);

CREATE FUNCTION mateerp_journal_guard() RETURNS trigger AS $$
DECLARE p accounting_accountingperiod; base text;
BEGIN
  PERFORM mateerp_financial_lock();
  IF TG_OP <> 'INSERT' AND OLD.status='posted' THEN
    RAISE EXCEPTION 'Posted journals are immutable' USING ERRCODE='23514';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  IF TG_OP='INSERT' AND NEW.status='posted' THEN
    RAISE EXCEPTION 'Create a draft before posting' USING ERRCODE='23514';
  END IF;
  IF NEW.status='posted' THEN
    SELECT base_currency INTO base FROM company_companyprofile WHERE id=1;
    SELECT * INTO p FROM accounting_accountingperiod WHERE id=NEW.period_id FOR UPDATE;
    IF NOT FOUND OR p.is_closed OR NEW.posting_date NOT BETWEEN p.start AND p."end"
       OR EXISTS(SELECT 1 FROM accounting_fiscalyear WHERE id=p.fiscal_year_id AND is_closed)
       OR NEW.base_currency<>base THEN
      RAISE EXCEPTION 'Closed, missing or incompatible posting period/currency' USING ERRCODE='23514';
    END IF;
    IF EXISTS(SELECT 1 FROM accounting_journalline l JOIN accounting_account a ON a.id=l.account_id
        WHERE l.journal_id=NEW.id AND (NOT a.is_active OR NOT a.is_postable OR (a.currency<>'' AND a.currency<>l.currency))) THEN
      RAISE EXCEPTION 'Inactive/summary/currency-incompatible account' USING ERRCODE='23514';
    END IF;
    IF NEW.reversal_of_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM accounting_journalentry WHERE id=NEW.reversal_of_id AND status='posted') THEN
      RAISE EXCEPTION 'Only posted journals may be reversed' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER journal_guard BEFORE INSERT OR UPDATE OR DELETE ON accounting_journalentry FOR EACH ROW EXECUTE FUNCTION mateerp_journal_guard();

CREATE FUNCTION mateerp_line_guard() RETURNS trigger AS $$
DECLARE j accounting_journalentry; base text;
BEGIN
  PERFORM mateerp_financial_lock();
  IF TG_OP<>'INSERT' THEN
    SELECT * INTO j FROM accounting_journalentry WHERE id=OLD.journal_id FOR UPDATE;
    IF j.status='posted' THEN RAISE EXCEPTION 'Posted lines are immutable' USING ERRCODE='23514'; END IF;
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  SELECT * INTO j FROM accounting_journalentry WHERE id=NEW.journal_id FOR UPDATE;
  IF j.status='posted' THEN RAISE EXCEPTION 'Cannot add/move posted lines' USING ERRCODE='23514'; END IF;
  base := j.base_currency;
  IF NEW.debit='NaN'::numeric OR NEW.credit='NaN'::numeric OR NEW.base_debit='NaN'::numeric OR NEW.base_credit='NaN'::numeric OR NEW.exchange_rate='NaN'::numeric
    OR NEW.debit<>round(NEW.debit,mateerp_minor(NEW.currency)) OR NEW.credit<>round(NEW.credit,mateerp_minor(NEW.currency))
    OR NEW.base_debit<>round(NEW.base_debit,mateerp_minor(base)) OR NEW.base_credit<>round(NEW.base_credit,mateerp_minor(base))
    OR (NEW.debit>0 AND (NEW.base_debit<=0 OR NEW.base_credit<>0)) OR (NEW.credit>0 AND (NEW.base_credit<=0 OR NEW.base_debit<>0))
    OR (NEW.currency=base AND (NEW.exchange_rate<>1 OR NEW.debit<>NEW.base_debit OR NEW.credit<>NEW.base_credit))
    OR NEW.valuation NOT IN ('spot','carrying','reversal') THEN
    RAISE EXCEPTION 'Invalid exact currency amounts' USING ERRCODE='23514';
  END IF;
  IF NEW.valuation='spot' AND (NEW.base_debit<>round(NEW.debit*NEW.exchange_rate,mateerp_minor(base)) OR NEW.base_credit<>round(NEW.credit*NEW.exchange_rate,mateerp_minor(base))) THEN
    RAISE EXCEPTION 'Invalid conversion snapshot' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER line_guard BEFORE INSERT OR UPDATE OR DELETE ON accounting_journalline FOR EACH ROW EXECUTE FUNCTION mateerp_line_guard();

CREATE FUNCTION mateerp_balanced() RETURNS trigger AS $$
DECLARE jid uuid; n bigint; d numeric; c numeric;
BEGIN
  jid := NEW.id;
  IF EXISTS(SELECT 1 FROM accounting_journalentry WHERE id=jid AND status='posted') THEN
    SELECT count(*),coalesce(sum(base_debit),0),coalesce(sum(base_credit),0) INTO n,d,c FROM accounting_journalline WHERE journal_id=jid;
    IF n<2 OR d<=0 OR d<>c THEN RAISE EXCEPTION 'Posted journal must balance exactly' USING ERRCODE='23514'; END IF;
    IF NEW.reversal_of_id IS NOT NULL AND EXISTS(
      (SELECT account_id,currency,debit,credit,base_debit,base_credit,exchange_rate,position FROM accounting_journalline WHERE journal_id=NEW.reversal_of_id
       EXCEPT ALL SELECT account_id,currency,credit,debit,base_credit,base_debit,exchange_rate,position FROM accounting_journalline WHERE journal_id=jid)
      UNION ALL
      (SELECT account_id,currency,credit,debit,base_credit,base_debit,exchange_rate,position FROM accounting_journalline WHERE journal_id=jid
       EXCEPT ALL SELECT account_id,currency,debit,credit,base_debit,base_credit,exchange_rate,position FROM accounting_journalline WHERE journal_id=NEW.reversal_of_id)
    ) THEN RAISE EXCEPTION 'Reversal must negate original lines exactly' USING ERRCODE='23514'; END IF;
  END IF;
  RETURN NULL;
END; $$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER journal_balanced AFTER INSERT OR UPDATE ON accounting_journalentry DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_balanced();

CREATE FUNCTION mateerp_account_guard() RETURNS trigger AS $$
DECLARE p bigint; t text; postable boolean; seen bigint[];
BEGIN
  PERFORM mateerp_financial_lock();
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  IF TG_OP='UPDATE' AND EXISTS(SELECT 1 FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id WHERE l.account_id=OLD.id AND j.status='posted')
    AND ROW(NEW.code,NEW.account_type,NEW.normal_side,NEW.parent_id,NEW.currency,NEW.subtype,NEW.control,NEW.is_postable) IS DISTINCT FROM ROW(OLD.code,OLD.account_type,OLD.normal_side,OLD.parent_id,OLD.currency,OLD.subtype,OLD.control,OLD.is_postable) THEN
    RAISE EXCEPTION 'Account historical meaning is locked' USING ERRCODE='23514';
  END IF;
  IF NEW.account_type NOT IN ('asset','liability','equity','revenue','expense') OR NEW.normal_side NOT IN ('debit','credit') THEN RAISE EXCEPTION 'Invalid account type/normal side' USING ERRCODE='23514'; END IF;
  IF NEW.is_postable AND EXISTS(SELECT 1 FROM accounting_account WHERE parent_id=NEW.id) THEN RAISE EXCEPTION 'Summary parent is not postable' USING ERRCODE='23514'; END IF;
  p:=NEW.parent_id; seen:=ARRAY[NEW.id];
  WHILE p IS NOT NULL LOOP
    IF p=ANY(seen) THEN RAISE EXCEPTION 'Account hierarchy cycle' USING ERRCODE='23514'; END IF;
    seen:=array_append(seen,p);
    SELECT parent_id,account_type,is_postable INTO p,t,postable FROM accounting_account WHERE id=p;
    IF t<>NEW.account_type OR postable THEN RAISE EXCEPTION 'Invalid account parent' USING ERRCODE='23514'; END IF;
  END LOOP;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER account_guard BEFORE INSERT OR UPDATE OR DELETE ON accounting_account FOR EACH ROW EXECUTE FUNCTION mateerp_account_guard();

CREATE FUNCTION mateerp_period_guard() RETURNS trigger AS $$
DECLARE y accounting_fiscalyear;
BEGIN
  PERFORM mateerp_financial_lock();
  SELECT * INTO y FROM accounting_fiscalyear WHERE id=NEW.fiscal_year_id;
  IF NEW.start<y.start OR NEW."end">y."end" OR (y.is_closed AND NOT NEW.is_closed) THEN RAISE EXCEPTION 'Period outside year or year is closed' USING ERRCODE='23514'; END IF;
  IF TG_OP='UPDATE' AND ROW(NEW.start,NEW."end",NEW.fiscal_year_id) IS DISTINCT FROM ROW(OLD.start,OLD."end",OLD.fiscal_year_id) AND EXISTS(SELECT 1 FROM accounting_journalentry WHERE period_id=OLD.id) THEN RAISE EXCEPTION 'Used period boundaries are immutable' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER period_guard BEFORE INSERT OR UPDATE ON accounting_accountingperiod FOR EACH ROW EXECUTE FUNCTION mateerp_period_guard();
CREATE FUNCTION mateerp_year_guard() RETURNS trigger AS $$
BEGIN
  PERFORM mateerp_financial_lock();
  IF TG_OP='UPDATE' AND ROW(NEW.start,NEW."end") IS DISTINCT FROM ROW(OLD.start,OLD."end") AND EXISTS(SELECT 1 FROM accounting_accountingperiod WHERE fiscal_year_id=OLD.id) THEN RAISE EXCEPTION 'Year boundaries are locked by periods' USING ERRCODE='23514'; END IF;
  IF NEW.is_closed AND EXISTS(SELECT 1 FROM accounting_accountingperiod WHERE fiscal_year_id=NEW.id AND NOT is_closed) THEN RAISE EXCEPTION 'Close child periods first' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER year_guard BEFORE INSERT OR UPDATE ON accounting_fiscalyear FOR EACH ROW EXECUTE FUNCTION mateerp_year_guard();

CREATE FUNCTION mateerp_company_history() RETURNS trigger AS $$
BEGIN
  IF EXISTS(SELECT 1 FROM accounting_journalentry WHERE status='posted') AND (TG_OP='DELETE' OR ROW(NEW.base_currency,NEW.fiscal_year_start_month) IS DISTINCT FROM ROW(OLD.base_currency,OLD.fiscal_year_start_month)) THEN RAISE EXCEPTION 'Financial history locks company currency and fiscal start' USING ERRCODE='23514'; END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER company_history BEFORE UPDATE OR DELETE ON company_companyprofile FOR EACH ROW EXECUTE FUNCTION mateerp_company_history();
CREATE TRIGGER fx_immutable BEFORE UPDATE OR DELETE ON accounting_exchangerate FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
CREATE TRIGGER tax_revision_immutable BEFORE UPDATE OR DELETE ON accounting_taxrevision FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
CREATE FUNCTION mateerp_approval_snapshot() RETURNS trigger AS $$
BEGIN
  IF OLD.action='accounting.post' AND ROW(NEW.payload,NEW.action,NEW.subject_key,NEW.requested_by_id) IS DISTINCT FROM ROW(OLD.payload,OLD.action,OLD.subject_key,OLD.requested_by_id) THEN RAISE EXCEPTION 'Financial approval snapshot is immutable' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER financial_approval_snapshot BEFORE UPDATE ON approvals_approvalrequest FOR EACH ROW EXECUTE FUNCTION mateerp_approval_snapshot();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0001_initial"),
        ("company", "0001_initial"),
        ("core", "0001_append_only_trigger_function"),
        ("approvals", "0002_remove_approvalrequest_one_pending_per_action_and_more"),
    ]
    operations = [migrations.RunSQL(SQL)]
