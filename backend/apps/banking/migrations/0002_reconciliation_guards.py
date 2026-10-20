from django.db import migrations

SQL = r"""
CREATE FUNCTION mateerp_bank_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF NOT EXISTS(SELECT 1 FROM accounting_account WHERE id=NEW.gl_account_id AND account_type='asset' AND is_postable AND currency=NEW.currency) THEN RAISE EXCEPTION 'Bank must link a currency-restricted posting asset' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND ROW(NEW.gl_account_id,NEW.currency,NEW.kind) IS DISTINCT FROM ROW(OLD.gl_account_id,OLD.currency,OLD.kind) AND EXISTS(SELECT 1 FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id WHERE l.account_id=OLD.gl_account_id AND j.status='posted') THEN RAISE EXCEPTION 'Bank financial identity is locked' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER bank_guard BEFORE INSERT OR UPDATE ON banking_bankaccount FOR EACH ROW EXECUTE FUNCTION mateerp_bank_guard();
CREATE FUNCTION mateerp_statement_guard() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF EXISTS(SELECT 1 FROM banking_reconciliation WHERE statement_id=OLD.id AND is_complete) THEN RAISE EXCEPTION 'Completed statement is immutable' USING ERRCODE='23514'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER statement_guard BEFORE UPDATE OR DELETE ON banking_bankstatement FOR EACH ROW EXECUTE FUNCTION mateerp_statement_guard();
CREATE FUNCTION mateerp_match_guard() RETURNS trigger AS $$
DECLARE rid bigint;
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_TABLE_NAME='banking_matchgroup' THEN
   IF TG_OP='INSERT' THEN rid:=NEW.reconciliation_id; ELSE rid:=OLD.reconciliation_id; END IF;
 ELSE
   IF TG_OP='INSERT' THEN SELECT reconciliation_id INTO rid FROM banking_matchgroup WHERE id=NEW.group_id;
   ELSE SELECT reconciliation_id INTO rid FROM banking_matchgroup WHERE id=OLD.group_id; END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM banking_reconciliation WHERE id=rid AND is_complete) THEN RAISE EXCEPTION 'Completed reconciliation matches are immutable' USING ERRCODE='23514'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER match_guard BEFORE INSERT OR UPDATE OR DELETE ON banking_matchgroup FOR EACH ROW EXECUTE FUNCTION mateerp_match_guard();
CREATE TRIGGER ledger_match_guard BEFORE INSERT OR UPDATE OR DELETE ON banking_ledgermatch FOR EACH ROW EXECUTE FUNCTION mateerp_match_guard();
CREATE TRIGGER statement_match_guard BEFORE INSERT OR UPDATE OR DELETE ON banking_statementmatch FOR EACH ROW EXECUTE FUNCTION mateerp_match_guard();
CREATE FUNCTION mateerp_match_balanced() RETURNS trigger AS $$
DECLARE gid bigint; sid bigint; aid bigint; cy text; s numeric; l numeric;
BEGIN
 gid:=NEW.group_id;
 SELECT r.statement_id INTO sid FROM banking_matchgroup g JOIN banking_reconciliation r ON r.id=g.reconciliation_id WHERE g.id=gid AND g.is_active;
 IF sid IS NULL THEN RETURN NULL; END IF;
 SELECT b.gl_account_id,b.currency INTO aid,cy FROM banking_bankstatement st JOIN banking_bankaccount b ON b.id=st.bank_account_id WHERE st.id=sid;
 SELECT sum(sl.amount) INTO s FROM banking_statementmatch m JOIN banking_statementline sl ON sl.id=m.line_id WHERE m.group_id=gid AND m.is_active;
 SELECT sum(jl.debit-jl.credit) INTO l FROM banking_ledgermatch m JOIN accounting_journalline jl ON jl.id=m.line_id WHERE m.group_id=gid AND m.is_active;
 IF s IS NULL OR l IS NULL OR s<>l OR EXISTS(SELECT 1 FROM banking_statementmatch m JOIN banking_statementline sl ON sl.id=m.line_id WHERE m.group_id=gid AND sl.statement_id<>sid)
 OR EXISTS(SELECT 1 FROM banking_ledgermatch m JOIN accounting_journalline jl ON jl.id=m.line_id JOIN accounting_journalentry j ON j.id=jl.journal_id WHERE m.group_id=gid AND (jl.account_id<>aid OR jl.currency<>cy OR j.status<>'posted')) THEN
 RAISE EXCEPTION 'Reconciliation group amounts/account/currency must agree' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END; $$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER ledger_match_balanced AFTER INSERT OR UPDATE ON banking_ledgermatch DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_match_balanced();
CREATE CONSTRAINT TRIGGER statement_match_balanced AFTER INSERT OR UPDATE ON banking_statementmatch DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_match_balanced();
"""


class Migration(migrations.Migration):
    dependencies = [("banking", "0001_initial"), ("accounting", "0002_integrity")]
    operations = [migrations.RunSQL(SQL)]
