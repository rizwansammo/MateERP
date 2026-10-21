from django.db import migrations


class Migration(migrations.Migration):
    dependencies=[('budgeting','0001_initial')]
    operations=[migrations.RunSQL('''
    CREATE TRIGGER classification_immutable BEFORE UPDATE OR DELETE ON budgeting_analyticalclassification
    FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
    CREATE TRIGGER budget_publication_immutable BEFORE UPDATE OR DELETE ON budgeting_budgetpublication
    FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
    CREATE TRIGGER budget_line_immutable BEFORE UPDATE OR DELETE ON budgeting_budgetline
    FOR EACH ROW EXECUTE FUNCTION mateerp_forbid_modification();
    CREATE FUNCTION mateerp_budget_revision_guard() RETURNS trigger AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Retain budget versions'; END IF;
      IF ROW(NEW.budget_id,NEW.version,NEW.notes,NEW.created_by_id,NEW.created_at)
       IS DISTINCT FROM ROW(OLD.budget_id,OLD.version,OLD.notes,OLD.created_by_id,OLD.created_at)
       OR OLD.status NOT IN ('draft','pending') OR NEW.status NOT IN ('draft','pending','approved','rejected')
      THEN RAISE EXCEPTION 'Budget revision identity is frozen'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER budget_revision_guard BEFORE UPDATE OR DELETE ON budgeting_budgetrevision
    FOR EACH ROW EXECUTE FUNCTION mateerp_budget_revision_guard();
    CREATE FUNCTION mateerp_budget_scope_guard() RETURNS trigger AS $$
    BEGIN
      PERFORM mateerp_financial_lock();
      IF TG_TABLE_NAME='budgeting_budget' THEN
        IF NEW.active_revision_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM budgeting_budgetrevision r
          WHERE r.id=NEW.active_revision_id AND r.budget_id=NEW.id AND r.status='approved')
        THEN RAISE EXCEPTION 'Active budget requires its approved revision'; END IF;
      END IF;
      IF EXISTS(SELECT 1 FROM budgeting_budgetline a JOIN budgeting_budget p ON p.active_revision_id=a.revision_id
        JOIN budgeting_budgetline b ON b.account_id=a.account_id AND b.month=a.month AND a.id<b.id
        JOIN budgeting_budget q ON q.active_revision_id=b.revision_id
        WHERE NOT p.is_archived AND NOT q.is_archived
          AND (a.cost_center_id IS NULL OR b.cost_center_id IS NULL OR a.cost_center_id=b.cost_center_id)
          AND (a.project_id IS NULL OR b.project_id IS NULL OR a.project_id=b.project_id))
      THEN RAISE EXCEPTION 'Active budget scopes overlap'; END IF;
      RETURN NULL;
    END; $$ LANGUAGE plpgsql;
    CREATE CONSTRAINT TRIGGER budget_scope_check AFTER INSERT OR UPDATE ON budgeting_budget
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_budget_scope_guard();
    CREATE CONSTRAINT TRIGGER budget_line_scope_check AFTER INSERT ON budgeting_budgetline
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mateerp_budget_scope_guard();
    ''','''
    DROP TRIGGER classification_immutable ON budgeting_analyticalclassification;
    DROP TRIGGER budget_publication_immutable ON budgeting_budgetpublication;
    DROP TRIGGER budget_line_immutable ON budgeting_budgetline;
    DROP TRIGGER budget_revision_guard ON budgeting_budgetrevision;
    DROP TRIGGER budget_scope_check ON budgeting_budget;
    DROP TRIGGER budget_line_scope_check ON budgeting_budgetline;
    DROP FUNCTION mateerp_budget_revision_guard(); DROP FUNCTION mateerp_budget_scope_guard();
    ''')]
