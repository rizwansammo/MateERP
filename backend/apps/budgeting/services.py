"""Management budgets and analytical overlays; never another ledger."""

import calendar
from datetime import date

from django.db import transaction
from django.db.models import (
    BigIntegerField,
    Case,
    CharField,
    F,
    Max,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounting.models import Account, FiscalYear, JournalLine
from apps.accounting.money import ZERO, money, strings
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.company.services import is_module_enabled
from apps.core.exceptions import BusinessRuleViolation
from apps.sales.calculation import allocate
from apps.sales.models import Project
from apps.sales.services import _get

from .models import (
    AnalyticalClassification,
    Budget,
    BudgetLine,
    BudgetPublication,
    BudgetRevision,
    CostCenter,
)

CATEGORIES = {"operating", "cogs", "capex", "tax"}


def enabled():
    if not is_module_enabled("budgeting"):
        raise BusinessRuleViolation(
            "Budgeting is disabled. Historical plans and actual reports remain readable."
        )


@transaction.atomic
def save_cost_center(request, data, pk=None):
    require(request.user, "budgets.manage", "finance.view")
    lock_company()
    enabled()
    obj = _get(CostCenter, pk) if pk else CostCenter()
    before = {k: getattr(obj, k) for k in data}
    for key, value in data.items():
        setattr(obj, key, value)
    obj.code = obj.code.strip().upper()
    if not set(obj.categories) <= CATEGORIES:
        raise ValidationError({"categories": "Choose valid budget categories."})
    obj.categories = sorted(set(obj.categories))
    obj.full_clean()
    obj.save()
    record("budget.cost_center_saved", request=request, target=obj, before=before, after=data)
    return obj


def _center(pk):
    obj = _get(CostCenter, pk) if pk else None
    if obj and not obj.is_active:
        raise ValidationError({"cost_center_id": "Choose an active cost center."})
    return obj


def _project(pk):
    return _get(Project, pk) if pk else None


@transaction.atomic
def classify(request, data):
    require(request.user, "budgets.manage", "finance.view")
    lock_company()
    enabled()
    line = _get(JournalLine, data["line_id"])
    if line.journal.status != "posted" or line.account.account_type not in ("expense", "asset"):
        raise BusinessRuleViolation(
            "Classify posted spending lines only. This does not change the original "
            "financial journal or its project identity."
        )
    if line.account.account_type == "asset" and not (
        line.account.control == "fixed_assets" or line.account.input_tax_revisions.exists()
    ):
        raise BusinessRuleViolation(
            "Only fixed-asset additions and recoverable taxes are spending dimensions; "
            "cash and working-capital balances are excluded."
        )
    version = (line.analytical_classifications.aggregate(v=Max("version"))["v"] or 0) + 1
    obj = AnalyticalClassification.objects.create(
        line=line,
        version=version,
        cost_center=_center(data.get("cost_center_id")),
        project=_project(data.get("project_id")),
        reason=data["reason"],
        created_by=request.user,
    )
    record(
        "budget.analytical_reclassification",
        request=request,
        target=obj,
        after={
            "line_id": line.pk,
            "version": version,
            "cost_center_id": obj.cost_center_id,
            "analytical_project_id": obj.project_id,
            "journal_changed": False,
        },
        reason=obj.reason,
    )
    return obj


def classified_lines(*, classification_as_of=None):
    """Current/as-at overlays, with acquisition attribution inherited by asset reclassifications.

    Reports disclose analytical classification. Original GL project dimensions are
    never changed; project profitability in the owning domain remains authoritative.
    """
    from apps.assets.models import Asset, AssetDisposal, CapitalizationReversal, DepreciationCharge
    from apps.banking.models import BankAccount

    tag = AnalyticalClassification.objects.filter(line_id=OuterRef("pk"))
    origin_tag = AnalyticalClassification.objects.filter(line_id=OuterRef("_origin_id"))
    if classification_as_of:
        tag = tag.filter(created_at__lte=classification_as_of)
        origin_tag = origin_tag.filter(created_at__lte=classification_as_of)
    tag, origin_tag = tag.order_by("-version"), origin_tag.order_by("-version")
    qs = JournalLine.objects.filter(journal__status="posted").exclude(
        account_id__in=BankAccount.objects.values("gl_account_id")
    )
    qs = qs.filter(
        Q(account__account_type="expense")
        | Q(account__control="fixed_assets")
        | Q(account__input_tax_revisions__isnull=False)
    ).distinct()
    qs = qs.annotate(
        _origin_id=Coalesce(
            Subquery(
                Asset.objects.filter(journal_id=OuterRef("journal_id")).values("source_line_id")[:1]
            ),
            Subquery(
                DepreciationCharge.objects.filter(journal_id=OuterRef("journal_id")).values(
                    "asset__source_line_id"
                )[:1]
            ),
            Subquery(
                AssetDisposal.objects.filter(journal_id=OuterRef("journal_id")).values(
                    "asset__source_line_id"
                )[:1]
            ),
            Subquery(
                CapitalizationReversal.objects.filter(journal_id=OuterRef("journal_id")).values(
                    "asset__source_line_id"
                )[:1]
            ),
            F("pk"),
            output_field=BigIntegerField(),
        )
    )
    qs = qs.annotate(
        _tag=Subquery(tag.values("pk")[:1]),
        _origin_tag=Subquery(origin_tag.values("pk")[:1]),
        _cc=Subquery(tag.values("cost_center_id")[:1]),
        _project=Subquery(tag.values("project_id")[:1]),
        _origin_cc=Subquery(origin_tag.values("cost_center_id")[:1]),
        _origin_project=Subquery(origin_tag.values("project_id")[:1]),
    )
    return qs.annotate(
        analytical_cost_center=Case(
            When(_tag__isnull=False, then=Cast("_cc", CharField())),
            When(_origin_tag__isnull=False, then=Cast("_origin_cc", CharField())),
            default=Value(None),
            output_field=CharField(),
        ),
        analytical_project=Case(
            When(_tag__isnull=False, then=Cast("_project", CharField())),
            When(_origin_tag__isnull=False, then=Cast("_origin_project", CharField())),
            default=KeyTextTransform("project", "dimensions"),
            output_field=CharField(),
        ),
    )


@transaction.atomic
def create_budget(request, data):
    require(request.user, "budgets.manage", "finance.view")
    lock_company()
    enabled()
    obj = Budget(
        name=data["name"],
        fiscal_year=_get(FiscalYear, data["fiscal_year_id"]),
        owner_reference=data.get("owner_reference", ""),
        created_by=request.user,
    )
    obj.full_clean()
    obj.save()
    record("budget.created", request=request, target=obj, after=data)
    return obj


def overlaps(a, b):
    return (
        a.month == b.month
        and a.account_id == b.account_id
        and (
            a.cost_center_id is None
            or b.cost_center_id is None
            or a.cost_center_id == b.cost_center_id
        )
        and (a.project_id is None or b.project_id is None or a.project_id == b.project_id)
    )


def _validate_category(account, category):
    valid = (
        (
            category in ("operating", "cogs")
            and account.account_type == "expense"
            and not account.control
        )
        or (category == "capex" and account.control == "fixed_assets")
        or (
            category == "tax"
            and account.account_type == "asset"
            and account.input_tax_revisions.exists()
        )
    )
    if not valid or not account.is_postable or not account.is_active:
        raise ValidationError(
            {
                "account_id": "Choose an active account appropriate to the category. "
                "CAPEX uses fixed-asset additions; recoverable tax is separate."
            }
        )


@transaction.atomic
def create_revision(request, budget_id, data):
    require(request.user, "budgets.manage", "finance.view")
    company = lock_company()
    enabled()
    budget = _get(Budget, budget_id)
    if budget.is_archived:
        raise BusinessRuleViolation("Restore this budget before creating another revision.")
    version = (budget.revisions.aggregate(v=Max("version"))["v"] or 0) + 1
    obj = BudgetRevision.objects.create(
        budget=budget, version=version, notes=data["notes"], created_by=request.user
    )
    created = []
    for row in data["lines"]:
        account = _get(Account, row["account_id"])
        _validate_category(account, row["category"])
        center, project = _center(row.get("cost_center_id")), _project(row.get("project_id"))
        if center and center.categories and row["category"] not in center.categories:
            raise ValidationError(
                {"cost_center_id": "This cost center does not cover the selected category."}
            )
        months = [row["month"]]
        if row.get("annual"):
            months = []
            year, month = budget.fiscal_year.start.year, budget.fiscal_year.start.month
            for n in range(12):
                y, m = divmod(year * 12 + month - 1 + n, 12)
                months.append(date(y, m + 1, 1))
        values = allocate(
            money(row["amount"], company.base_currency), [1] * len(months), company.base_currency
        )
        for on, value in zip(months, values, strict=True):
            if on.day != 1 or on < budget.fiscal_year.start or on > budget.fiscal_year.end:
                raise ValidationError(
                    {"month": "Use a first-of-month date within the selected fiscal year."}
                )
            line = BudgetLine(
                revision=obj,
                month=on,
                account=account,
                category=row["category"],
                cost_center=center,
                project=project,
                amount=value,
            )
            if any(overlaps(line, other) for other in created):
                raise BusinessRuleViolation(
                    "Budget lines overlap the same account/month/spending scope, "
                    "even if category labels differ."
                )
            line.full_clean()
            line.save()
            created.append(line)
    record(
        "budget.revision_created",
        request=request,
        target=obj,
        after={"version": version, "lines": len(created)},
        reason=obj.notes,
    )
    return obj


@transaction.atomic
def submit_revision(request, revision_id):
    require(request.user, "budgets.manage", "finance.view")
    lock_company()
    enabled()
    obj = _get(BudgetRevision, revision_id)
    if obj.status != "draft" or not obj.lines.exists():
        raise BusinessRuleViolation("Submit a nonempty draft revision.")
    obj.approval = approvals.submit(
        request,
        action="budget.publish",
        subject_key=f"budget-revision:{obj.pk}",
        title=f"Approve {obj.budget.name} v{obj.version}",
        reason=obj.notes[:500],
        payload={"revision_id": obj.pk},
    )
    obj.status = "pending"
    obj.save(update_fields=["approval", "status"])
    return obj


def execute_approval(request, approval, approver):
    obj = _get(BudgetRevision, approval.payload["revision_id"])
    if approver.pk == obj.created_by_id:
        raise PermissionDenied(
            "An independent authorized user must approve the budget creator’s revision."
        )
    budget = obj.budget
    if (
        obj.status != "pending"
        or budget.is_archived
        or (budget.active_revision_id and budget.active_revision.version >= obj.version)
    ):
        raise BusinessRuleViolation("This revision is no longer eligible for publication.")
    lines = list(obj.lines.all())
    others = BudgetLine.objects.filter(
        revision_id__in=Budget.objects.filter(is_archived=False)
        .exclude(pk=budget.pk)
        .values("active_revision_id")
    )
    for line in lines:
        for other in others.filter(account_id=line.account_id, month=line.month):
            if overlaps(line, other):
                raise BusinessRuleViolation(
                    "Another active budget already covers this account/month/spending scope."
                )
    BudgetPublication.objects.create(
        budget=budget, revision=obj, previous=budget.active_revision, actor=approver
    )
    obj.status = "approved"
    obj.save(update_fields=["status"])
    budget.active_revision = obj
    if budget.original_revision_id is None:
        budget.original_revision = obj
    budget.save(update_fields=["active_revision", "original_revision"])
    record(
        "budget.revision_published",
        request=request,
        target=obj,
        after={"version": obj.version, "budget_id": budget.pk},
    )
    return f"budget_revision:{obj.pk}"


def declined(request, approval):
    obj = _get(BudgetRevision, approval.payload["revision_id"])
    obj.status = "rejected"
    obj.save(update_fields=["status"])


@transaction.atomic
def archive(request, pk, archived):
    require(request.user, "budgets.manage", "budgets.approve", "finance.view")
    lock_company()
    obj = _get(Budget, pk)
    if not archived and obj.is_archived and obj.active_revision_id:
        others = BudgetLine.objects.filter(
            revision_id__in=Budget.objects.filter(is_archived=False)
            .exclude(pk=obj.pk)
            .values("active_revision_id")
        )
        if any(
            overlaps(a, b)
            for a in obj.active_revision.lines.all()
            for b in others.filter(account_id=a.account_id, month=a.month)
        ):
            raise BusinessRuleViolation(
                "Another active budget now reserves this scope. "
                "Approve a non-overlapping revision instead."
            )
    obj.is_archived = archived
    obj.save(update_fields=["is_archived"])
    record("budget.archived", request=request, target=obj, after={"archived": archived})
    return obj


def line_actuals(line, *, classification_as_of=None):
    end = line.month.replace(day=calendar.monthrange(line.month.year, line.month.month)[1])
    qs = classified_lines(classification_as_of=classification_as_of).filter(
        account_id=line.account_id,
        journal__posting_date__gte=line.month,
        journal__posting_date__lte=end,
    )
    if line.cost_center_id:
        qs = qs.filter(analytical_cost_center=str(line.cost_center_id))
    if line.project_id:
        qs = qs.filter(analytical_project=str(line.project_id))
    if line.category == "capex":
        from apps.assets.models import CapitalizationReversal

        qs = qs.filter(
            Q(base_debit__gt=0)
            | Q(journal_id__in=CapitalizationReversal.objects.values("journal_id"))
        )
    return qs


@transaction.atomic
def comparison(revision, *, classification_as_of=None):
    lock_company()
    original = (
        list(revision.budget.original_revision.lines.all())
        if revision.budget.original_revision_id
        else []
    )
    out = []
    for line in revision.lines.select_related("account", "cost_center", "project").order_by(
        "month", "account__code", "pk"
    ):
        rows = line_actuals(line, classification_as_of=classification_as_of)
        sums = rows.aggregate(d=Sum("base_debit"), c=Sum("base_credit"))
        actual = (sums["d"] or ZERO) - (sums["c"] or ZERO)
        first = sum(
            (
                original_line.amount
                for original_line in original
                if original_line.month == line.month
                and original_line.account_id == line.account_id
                and original_line.cost_center_id == line.cost_center_id
                and original_line.project_id == line.project_id
            ),
            ZERO,
        )
        out.append(
            {
                "id": line.pk,
                "month": line.month,
                "account_id": line.account_id,
                "account_code": line.account.code,
                "account_name": line.account.name,
                "category": line.category,
                "cost_center_id": line.cost_center_id,
                "cost_center": str(line.cost_center) if line.cost_center else None,
                "project_id": line.project_id,
                "original": first,
                "revised": line.amount,
                "actual": actual,
                "remaining": line.amount - actual,
                "variance": actual - line.amount,
                "over_budget": actual > line.amount,
            }
        )
    return strings(out)
