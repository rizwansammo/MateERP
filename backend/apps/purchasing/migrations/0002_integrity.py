from django.db import migrations

# Posted payable documents keep their amounts; only settlement totals, status and
# the void link change after posting.
SQL = r"""
CREATE FUNCTION mateerp_posted_payable_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.number IS NOT NULL OR OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Posted or decided payables cannot be deleted' USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.number IS NOT NULL AND ROW(NEW.number, NEW.vendor_id, NEW.currency, NEW.taxable,
       NEW.tax, NEW.total, NEW.exchange_rate, NEW.base_total, NEW.journal_id)
     IS DISTINCT FROM ROW(OLD.number, OLD.vendor_id, OLD.currency, OLD.taxable, OLD.tax,
       OLD.total, OLD.exchange_rate, OLD.base_total, OLD.journal_id) THEN
    RAISE EXCEPTION 'Posted payable content is immutable' USING ERRCODE = '23514';
  END IF;
  IF OLD.void_journal_id IS NOT NULL AND NEW.void_journal_id IS DISTINCT FROM OLD.void_journal_id THEN
    RAISE EXCEPTION 'A void is final' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER posted_bill_guard BEFORE UPDATE OR DELETE ON purchasing_vendorbill
  FOR EACH ROW EXECUTE FUNCTION mateerp_posted_payable_guard();
CREATE TRIGGER posted_expense_guard BEFORE UPDATE OR DELETE ON purchasing_expense
  FOR EACH ROW EXECUTE FUNCTION mateerp_posted_payable_guard();

CREATE FUNCTION mateerp_posted_bill_line_guard() RETURNS trigger AS $$
DECLARE posted boolean;
BEGIN
  SELECT number IS NOT NULL INTO posted FROM purchasing_vendorbill
    WHERE id = COALESCE(OLD.bill_id, NEW.bill_id);
  IF posted THEN
    RAISE EXCEPTION 'Posted bill lines are immutable' USING ERRCODE = '23514';
  END IF;
  RETURN COALESCE(NEW, OLD);
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER posted_bill_line_guard BEFORE INSERT OR UPDATE OR DELETE ON purchasing_vendorbillline
  FOR EACH ROW EXECUTE FUNCTION mateerp_posted_bill_line_guard();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS posted_bill_line_guard ON purchasing_vendorbillline;
DROP FUNCTION IF EXISTS mateerp_posted_bill_line_guard();
DROP TRIGGER IF EXISTS posted_expense_guard ON purchasing_expense;
DROP TRIGGER IF EXISTS posted_bill_guard ON purchasing_vendorbill;
DROP FUNCTION IF EXISTS mateerp_posted_payable_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
