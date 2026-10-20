from django.db import migrations

# Issued receivable documents are immutable at the database level. Only running
# settlement totals, status and the write-once PDF link may change after issue.
SQL = r"""
CREATE FUNCTION mateerp_issued_invoice_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' OR OLD.number IS NOT NULL THEN
      RAISE EXCEPTION 'Issued or decided invoices cannot be deleted' USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.number IS NOT NULL AND ROW(NEW.number, NEW.customer_id, NEW.currency, NEW.issue_date,
       NEW.due_date, NEW.subtotal, NEW.line_discount, NEW.document_discount, NEW.taxable, NEW.tax,
       NEW.total, NEW.exchange_rate, NEW.base_total, NEW.snapshot, NEW.branding_version_id,
       NEW.journal_id, NEW.issued_at, NEW.prices_include_tax)
     IS DISTINCT FROM ROW(OLD.number, OLD.customer_id, OLD.currency, OLD.issue_date,
       OLD.due_date, OLD.subtotal, OLD.line_discount, OLD.document_discount, OLD.taxable, OLD.tax,
       OLD.total, OLD.exchange_rate, OLD.base_total, OLD.snapshot, OLD.branding_version_id,
       OLD.journal_id, OLD.issued_at, OLD.prices_include_tax) THEN
    RAISE EXCEPTION 'Issued invoice content is immutable' USING ERRCODE = '23514';
  END IF;
  IF OLD.pdf_file_id IS NOT NULL AND NEW.pdf_file_id IS DISTINCT FROM OLD.pdf_file_id THEN
    RAISE EXCEPTION 'The official PDF of an invoice is write-once' USING ERRCODE = '23514';
  END IF;
  IF OLD.void_journal_id IS NOT NULL AND NEW.void_journal_id IS DISTINCT FROM OLD.void_journal_id THEN
    RAISE EXCEPTION 'An invoice void is final' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER issued_invoice_guard BEFORE UPDATE OR DELETE ON billing_invoice
  FOR EACH ROW EXECUTE FUNCTION mateerp_issued_invoice_guard();

CREATE FUNCTION mateerp_issued_invoice_line_guard() RETURNS trigger AS $$
DECLARE issued boolean;
BEGIN
  SELECT number IS NOT NULL INTO issued FROM billing_invoice
    WHERE id = COALESCE(OLD.invoice_id, NEW.invoice_id);
  IF issued THEN
    IF TG_OP = 'DELETE' THEN
      RAISE EXCEPTION 'Issued invoice lines cannot be deleted' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' THEN
      RAISE EXCEPTION 'Issued invoices cannot gain lines' USING ERRCODE = '23514';
    END IF;
    IF ROW(NEW.invoice_id, NEW.position, NEW.description, NEW.quantity, NEW.unit_price,
         NEW.discount_type, NEW.discount_value, NEW.tax_code_id, NEW.revenue_account_id,
         NEW.subtotal, NEW.line_discount, NEW.document_discount, NEW.taxable, NEW.tax, NEW.total,
         NEW.tax_rate, NEW.tax_revision_id)
       IS DISTINCT FROM ROW(OLD.invoice_id, OLD.position, OLD.description, OLD.quantity,
         OLD.unit_price, OLD.discount_type, OLD.discount_value, OLD.tax_code_id,
         OLD.revenue_account_id, OLD.subtotal, OLD.line_discount, OLD.document_discount,
         OLD.taxable, OLD.tax, OLD.total, OLD.tax_rate, OLD.tax_revision_id) THEN
      RAISE EXCEPTION 'Issued invoice lines are immutable' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN COALESCE(NEW, OLD);
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER issued_invoice_line_guard BEFORE INSERT OR UPDATE OR DELETE ON billing_invoiceline
  FOR EACH ROW EXECUTE FUNCTION mateerp_issued_invoice_line_guard();

CREATE FUNCTION mateerp_issued_document_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Issued documents cannot be deleted' USING ERRCODE = '23514';
  END IF;
  IF OLD.number IS NOT NULL AND (NEW.number IS DISTINCT FROM OLD.number
      OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
      OR NEW.branding_version_id IS DISTINCT FROM OLD.branding_version_id) THEN
    RAISE EXCEPTION 'Issued document content is immutable' USING ERRCODE = '23514';
  END IF;
  IF OLD.pdf_file_id IS NOT NULL AND NEW.pdf_file_id IS DISTINCT FROM OLD.pdf_file_id THEN
    RAISE EXCEPTION 'The official PDF is write-once' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER issued_receipt_guard BEFORE UPDATE OR DELETE ON billing_moneyreceipt
  FOR EACH ROW EXECUTE FUNCTION mateerp_issued_document_guard();
CREATE TRIGGER issued_credit_note_guard BEFORE UPDATE OR DELETE ON billing_creditnote
  FOR EACH ROW EXECUTE FUNCTION mateerp_issued_document_guard();
CREATE TRIGGER credit_movement_append_only BEFORE UPDATE OR DELETE ON billing_customercreditmovement
  FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
CREATE TRIGGER credit_application_append_only BEFORE UPDATE OR DELETE ON billing_creditapplication
  FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS credit_application_append_only ON billing_creditapplication;
DROP TRIGGER IF EXISTS credit_movement_append_only ON billing_customercreditmovement;
DROP TRIGGER IF EXISTS issued_credit_note_guard ON billing_creditnote;
DROP TRIGGER IF EXISTS issued_receipt_guard ON billing_moneyreceipt;
DROP FUNCTION IF EXISTS mateerp_issued_document_guard();
DROP TRIGGER IF EXISTS issued_invoice_line_guard ON billing_invoiceline;
DROP FUNCTION IF EXISTS mateerp_issued_invoice_line_guard();
DROP TRIGGER IF EXISTS issued_invoice_guard ON billing_invoice;
DROP FUNCTION IF EXISTS mateerp_issued_invoice_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial"), ("core", "0001_append_only_trigger_function")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
