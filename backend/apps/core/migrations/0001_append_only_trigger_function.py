"""Shared PostgreSQL trigger function used to make tables append-only.

Tables that hold historical evidence (audit events, published branding
versions) attach this function as a BEFORE UPDATE OR DELETE trigger, so the
database itself refuses to rewrite history even if application code tries.
"""

from django.db import migrations

CREATE = """
CREATE OR REPLACE FUNCTION mateerp_forbid_modification() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table % is append-only; % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

DROP = "DROP FUNCTION IF EXISTS mateerp_forbid_modification();"


class Migration(migrations.Migration):
    initial = True
    dependencies: list = []
    operations = [migrations.RunSQL(CREATE, DROP)]
