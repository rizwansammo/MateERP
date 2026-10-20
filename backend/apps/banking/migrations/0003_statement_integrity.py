from django.db import migrations

SQL = r"""
CREATE FUNCTION mateerp_statement_line_guard() RETURNS trigger AS $$
DECLARE sid bigint; st banking_bankstatement; cy text;
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='INSERT' THEN sid:=NEW.statement_id; ELSE sid:=OLD.statement_id; END IF;
 SELECT * INTO st FROM banking_bankstatement WHERE id=sid FOR UPDATE;
 IF EXISTS(SELECT 1 FROM banking_reconciliation WHERE statement_id=sid AND is_complete) THEN RAISE EXCEPTION 'Completed statement lines are immutable' USING ERRCODE='23514'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 IF TG_OP='UPDATE' AND EXISTS(SELECT 1 FROM banking_statementmatch WHERE line_id=OLD.id AND is_active) THEN RAISE EXCEPTION 'Unmatch before changing a statement line' USING ERRCODE='23514'; END IF;
 SELECT currency INTO cy FROM banking_bankaccount WHERE id=st.bank_account_id;
 IF NEW.statement_id<>sid OR NEW.date NOT BETWEEN st.start AND st."end" OR NEW.amount=0 OR NEW.amount='NaN'::numeric OR NEW.amount<>round(NEW.amount,mateerp_minor(cy)) THEN RAISE EXCEPTION 'Invalid statement amount, date or identity' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER statement_line_guard BEFORE INSERT OR UPDATE OR DELETE ON banking_statementline FOR EACH ROW EXECUTE FUNCTION mateerp_statement_line_guard();

CREATE FUNCTION mateerp_reconciliation_guard() RETURNS trigger AS $$
DECLARE st banking_bankstatement; aid bigint; net numeric; book numeric; unmatched numeric;
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='UPDATE' AND (NEW.statement_id<>OLD.statement_id OR (OLD.is_complete AND NEW.is_complete AND NEW IS DISTINCT FROM OLD)) THEN RAISE EXCEPTION 'Reconciliation identity/evidence is frozen' USING ERRCODE='23514'; END IF;
 IF NEW.is_complete THEN
   SELECT * INTO st FROM banking_bankstatement WHERE id=NEW.statement_id;
   SELECT gl_account_id INTO aid FROM banking_bankaccount WHERE id=st.bank_account_id;
   SELECT coalesce(sum(amount),0) INTO net FROM banking_statementline WHERE statement_id=st.id;
   IF st.opening_balance+net<>st.closing_balance OR EXISTS(SELECT 1 FROM banking_statementline sl WHERE sl.statement_id=st.id AND NOT EXISTS(SELECT 1 FROM banking_statementmatch m WHERE m.line_id=sl.id AND m.is_active)) THEN RAISE EXCEPTION 'Statement arithmetic or unmatched statement lines prevent completion' USING ERRCODE='23514'; END IF;
   SELECT coalesce(sum(l.debit-l.credit),0) INTO book FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id WHERE l.account_id=aid AND j.status='posted' AND j.posting_date<=st."end";
   SELECT coalesce(sum(l.debit-l.credit),0) INTO unmatched FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id WHERE l.account_id=aid AND j.status='posted' AND j.posting_date<=st."end" AND NOT EXISTS(SELECT 1 FROM banking_ledgermatch m WHERE m.line_id=l.id AND m.is_active);
   IF book<>st.closing_balance+unmatched OR NEW.completed_at IS NULL OR NEW.completed_by_id IS NULL THEN RAISE EXCEPTION 'Reconciliation equation/metadata is invalid' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER reconciliation_guard BEFORE INSERT OR UPDATE ON banking_reconciliation FOR EACH ROW EXECUTE FUNCTION mateerp_reconciliation_guard();
CREATE TRIGGER posting_identity_immutable BEFORE UPDATE OR DELETE ON accounting_postingidentity FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
ALTER TABLE accounting_exchangerate ADD CONSTRAINT fx_finite CHECK (value<>'NaN'::numeric);
"""


class Migration(migrations.Migration):
    dependencies = [("banking", "0002_reconciliation_guards")]
    operations = [migrations.RunSQL(SQL)]
