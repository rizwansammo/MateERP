from django.db import migrations, models

SQL = r"""
CREATE FUNCTION mateerp_credit_request_identity_guard() RETURNS trigger AS $$
BEGIN
  IF ROW(NEW.client_key, NEW.fingerprint) IS DISTINCT FROM ROW(OLD.client_key, OLD.fingerprint) THEN
    RAISE EXCEPTION 'Financial request identity is immutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER credit_request_identity BEFORE UPDATE ON billing_creditnote
  FOR EACH ROW EXECUTE FUNCTION mateerp_credit_request_identity_guard();
CREATE TRIGGER refund_request_identity BEFORE UPDATE ON billing_refund
  FOR EACH ROW EXECUTE FUNCTION mateerp_credit_request_identity_guard();
"""
REVERSE = r"""
DROP TRIGGER IF EXISTS credit_request_identity ON billing_creditnote;
DROP TRIGGER IF EXISTS refund_request_identity ON billing_refund;
DROP FUNCTION IF EXISTS mateerp_credit_request_identity_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_integrity")]
    operations = [
        migrations.AddField(
            model_name=name,
            name="fingerprint",
            field=models.CharField(blank=True, default="", max_length=64),
            preserve_default=False,
        )
        for name in ("creditnote", "creditapplication", "refund")
    ] + [migrations.RunSQL(SQL, REVERSE)]
