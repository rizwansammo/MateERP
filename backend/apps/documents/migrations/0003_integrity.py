from django.db import migrations

# Filed documents are never deleted. Generated documents never change; uploads keep
# their file, area and kind but may be re-filed or archived with a reason.
SQL = r"""
CREATE FUNCTION mateerp_filed_document_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Filed documents are retained; archive instead' USING ERRCODE = '23514';
  END IF;
  IF OLD.generated AND ROW(NEW.*) IS DISTINCT FROM ROW(OLD.*) THEN
    RAISE EXCEPTION 'Generated documents are immutable' USING ERRCODE = '23514';
  END IF;
  IF ROW(NEW.file_id, NEW.area, NEW.kind, NEW.generated, NEW.restricted, NEW.uploaded_by_id, NEW.created_at)
     IS DISTINCT FROM ROW(OLD.file_id, OLD.area, OLD.kind, OLD.generated, OLD.restricted,
       OLD.uploaded_by_id, OLD.created_at) THEN
    RAISE EXCEPTION 'A filed document keeps its file, area and kind' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER filed_document_guard BEFORE UPDATE OR DELETE ON documents_fileddocument
  FOR EACH ROW EXECUTE FUNCTION mateerp_filed_document_guard();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS filed_document_guard ON documents_fileddocument;
DROP FUNCTION IF EXISTS mateerp_filed_document_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("documents", "0002_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
