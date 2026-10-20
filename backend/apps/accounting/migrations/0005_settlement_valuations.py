from django.db import migrations

# Phase 4 adds two explicit valuation kinds besides spot/carrying/reversal:
# - historical: a settlement removing a document's base at its historical rate
#   (exact remainder on final settlement);
# - allocated: an exact proportional split of one converted document total.
# Both are exact in base minor units; only spot lines re-check the conversion.
BODY = r"""
CREATE OR REPLACE FUNCTION mateerp_line_guard() RETURNS trigger AS $$
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
    OR NEW.valuation NOT IN ({valuations}) THEN
    RAISE EXCEPTION 'Invalid exact currency amounts' USING ERRCODE='23514';
  END IF;
  IF NEW.valuation='spot' AND (NEW.base_debit<>round(NEW.debit*NEW.exchange_rate,mateerp_minor(base)) OR NEW.base_credit<>round(NEW.credit*NEW.exchange_rate,mateerp_minor(base))) THEN
    RAISE EXCEPTION 'Invalid conversion snapshot' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
"""

FORWARD = BODY.replace("{valuations}", "'spot','carrying','reversal','historical','allocated'")
PHASE3 = BODY.replace("{valuations}", "'spot','carrying','reversal'")


class Migration(migrations.Migration):
    dependencies = [("accounting", "0004_subledger_controls")]
    operations = [migrations.RunSQL(FORWARD, PHASE3)]
