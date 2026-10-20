from django.db import migrations

SQL = r"""
CREATE FUNCTION mateerp_bank_history_posting() RETURNS trigger AS $$
BEGIN
 IF NEW.status='posted' AND EXISTS(
   SELECT 1 FROM accounting_journalline l JOIN banking_bankaccount b ON b.gl_account_id=l.account_id
   JOIN banking_bankstatement st ON st.bank_account_id=b.id
   JOIN banking_reconciliation r ON r.statement_id=st.id
   WHERE l.journal_id=NEW.id AND r.is_complete AND NEW.posting_date<=st."end") THEN
   RAISE EXCEPTION 'Reopen bank reconciliation before posting into its history' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER bank_history_posting BEFORE UPDATE ON accounting_journalentry FOR EACH ROW EXECUTE FUNCTION mateerp_bank_history_posting();

CREATE FUNCTION mateerp_statement_sequence() RETURNS trigger AS $$
DECLARE prev banking_bankstatement; cy text; aid bigint; expected numeric;
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='UPDATE' AND ROW(NEW.bank_account_id,NEW.start,NEW."end",NEW.opening_balance,NEW.closing_balance)
     IS DISTINCT FROM ROW(OLD.bank_account_id,OLD.start,OLD."end",OLD.opening_balance,OLD.closing_balance) THEN
   RAISE EXCEPTION 'Statement financial identity is immutable' USING ERRCODE='23514';
 END IF;
 SELECT currency,gl_account_id INTO cy,aid FROM banking_bankaccount WHERE id=NEW.bank_account_id;
 IF NEW.opening_balance='NaN'::numeric OR NEW.closing_balance='NaN'::numeric OR NEW.opening_balance<>round(NEW.opening_balance,mateerp_minor(cy)) OR NEW.closing_balance<>round(NEW.closing_balance,mateerp_minor(cy)) THEN RAISE EXCEPTION 'Invalid statement precision' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
   SELECT * INTO prev FROM banking_bankstatement WHERE bank_account_id=NEW.bank_account_id ORDER BY "end" DESC LIMIT 1;
   IF FOUND THEN
     IF NEW.start<>prev."end"+1 THEN RAISE EXCEPTION 'Statement ranges must be sequential and contiguous' USING ERRCODE='23514'; END IF;
     expected:=prev.closing_balance;
   ELSE
     SELECT coalesce(sum(l.debit-l.credit),0) INTO expected FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id WHERE l.account_id=aid AND j.status='posted' AND j.posting_date<NEW.start;
   END IF;
   IF NEW.opening_balance<>expected THEN RAISE EXCEPTION 'Statement opening does not match its baseline' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER statement_sequence BEFORE INSERT OR UPDATE ON banking_bankstatement FOR EACH ROW EXECUTE FUNCTION mateerp_statement_sequence();

CREATE OR REPLACE FUNCTION mateerp_reconciliation_guard() RETURNS trigger AS $$
DECLARE st banking_bankstatement; aid bigint; net numeric; book numeric; unmatched numeric; baseline date; initial_opening numeric;
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='UPDATE' AND (NEW.statement_id<>OLD.statement_id OR (OLD.is_complete AND NEW.is_complete AND NEW IS DISTINCT FROM OLD)) THEN RAISE EXCEPTION 'Reconciliation identity/evidence is frozen' USING ERRCODE='23514'; END IF;
 IF jsonb_typeof(NEW.evidence)<>'array' THEN RAISE EXCEPTION 'Evidence must be a sequence' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND (SELECT coalesce(jsonb_agg(value ORDER BY ord),'[]'::jsonb) FROM jsonb_array_elements(NEW.evidence) WITH ORDINALITY t(value,ord) WHERE ord<=jsonb_array_length(OLD.evidence)) IS DISTINCT FROM OLD.evidence THEN RAISE EXCEPTION 'Earlier reconciliation evidence is immutable' USING ERRCODE='23514'; END IF;
 IF NEW.is_complete THEN
   SELECT * INTO st FROM banking_bankstatement WHERE id=NEW.statement_id;
   SELECT gl_account_id INTO aid FROM banking_bankaccount WHERE id=st.bank_account_id;
   SELECT start,opening_balance INTO baseline,initial_opening FROM banking_bankstatement WHERE bank_account_id=st.bank_account_id ORDER BY start LIMIT 1;
   SELECT coalesce(sum(l.debit-l.credit),0) INTO book FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id WHERE l.account_id=aid AND j.status='posted' AND j.posting_date<baseline;
   IF book<>initial_opening OR EXISTS(SELECT 1 FROM banking_reconciliation r JOIN banking_bankstatement s ON s.id=r.statement_id WHERE s.bank_account_id=st.bank_account_id AND s."end"<st.start AND NOT r.is_complete) THEN RAISE EXCEPTION 'Invalid opening baseline or earlier incomplete statement' USING ERRCODE='23514'; END IF;
   SELECT coalesce(sum(amount),0) INTO net FROM banking_statementline WHERE statement_id=st.id;
   IF st.opening_balance+net<>st.closing_balance OR EXISTS(SELECT 1 FROM banking_statementline sl WHERE sl.statement_id=st.id AND NOT EXISTS(SELECT 1 FROM banking_statementmatch m WHERE m.line_id=sl.id AND m.is_active)) THEN RAISE EXCEPTION 'Statement arithmetic or unmatched lines prevent completion' USING ERRCODE='23514'; END IF;
   SELECT coalesce(sum(l.debit-l.credit),0) INTO book FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id WHERE l.account_id=aid AND j.status='posted' AND j.posting_date<=st."end";
   SELECT coalesce(sum(l.debit-l.credit),0) INTO unmatched FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id WHERE l.account_id=aid AND j.status='posted' AND j.posting_date BETWEEN baseline AND st."end" AND NOT EXISTS(SELECT 1 FROM banking_ledgermatch m JOIN banking_matchgroup g ON g.id=m.group_id JOIN banking_reconciliation r ON r.id=g.reconciliation_id JOIN banking_bankstatement s ON s.id=r.statement_id WHERE m.line_id=l.id AND m.is_active AND s."end"<=st."end");
   IF book<>st.closing_balance+unmatched OR NEW.completed_at IS NULL OR NEW.completed_by_id IS NULL THEN RAISE EXCEPTION 'Reconciliation equation/metadata is invalid' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE FUNCTION mateerp_match_identity() RETURNS trigger AS $$
BEGIN
 PERFORM mateerp_financial_lock();
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Retain match history; deactivate while open' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='banking_matchgroup' THEN
   IF NEW.reconciliation_id<>OLD.reconciliation_id THEN RAISE EXCEPTION 'Match identity cannot move' USING ERRCODE='23514'; END IF;
 ELSE
   IF NEW.group_id<>OLD.group_id OR NEW.line_id<>OLD.line_id THEN RAISE EXCEPTION 'Match membership cannot move' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER match_identity BEFORE UPDATE OR DELETE ON banking_matchgroup FOR EACH ROW EXECUTE FUNCTION mateerp_match_identity();
CREATE TRIGGER ledger_match_identity BEFORE UPDATE OR DELETE ON banking_ledgermatch FOR EACH ROW EXECUTE FUNCTION mateerp_match_identity();
CREATE TRIGGER statement_match_identity BEFORE UPDATE OR DELETE ON banking_statementmatch FOR EACH ROW EXECUTE FUNCTION mateerp_match_identity();

CREATE FUNCTION mateerp_match_state() RETURNS trigger AS $$
DECLARE gid bigint; active boolean;
BEGIN
 IF TG_TABLE_NAME='banking_matchgroup' THEN gid:=NEW.id; ELSE gid:=NEW.group_id; END IF;
 SELECT is_active INTO active FROM banking_matchgroup WHERE id=gid;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF EXISTS(SELECT 1 FROM banking_statementmatch WHERE group_id=gid AND is_active<>active)
 OR EXISTS(SELECT 1 FROM banking_ledgermatch WHERE group_id=gid AND is_active<>active)
 OR (active AND (NOT EXISTS(SELECT 1 FROM banking_statementmatch WHERE group_id=gid) OR NOT EXISTS(SELECT 1 FROM banking_ledgermatch WHERE group_id=gid))) THEN RAISE EXCEPTION 'Match group and memberships must change together' USING ERRCODE='23514'; END IF;
 IF active AND EXISTS(SELECT 1 FROM banking_ledgermatch m JOIN accounting_journalline l ON l.id=m.line_id JOIN accounting_journalentry j ON j.id=l.journal_id JOIN banking_matchgroup g ON g.id=m.group_id JOIN banking_reconciliation r ON r.id=g.reconciliation_id JOIN banking_bankstatement s ON s.id=r.statement_id WHERE m.group_id=gid AND j.posting_date>s."end") THEN RAISE EXCEPTION 'Cannot match a future ledger movement' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END; $$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER match_state AFTER INSERT OR UPDATE ON banking_matchgroup DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_match_state();
CREATE CONSTRAINT TRIGGER ledger_match_state AFTER INSERT OR UPDATE ON banking_ledgermatch DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_match_state();
CREATE CONSTRAINT TRIGGER statement_match_state AFTER INSERT OR UPDATE ON banking_statementmatch DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_match_state();
"""


class Migration(migrations.Migration):
    dependencies = [("banking", "0003_statement_integrity")]
    operations = [migrations.RunSQL(SQL)]
