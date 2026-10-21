"""Classify the existing authoritative cash movement statement without another ledger."""

from django.db import transaction
from django.db.models import Exists, F, Max, OuterRef, Subquery, Sum, UUIDField
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from apps.accounting.models import JournalEntry, JournalLine
from apps.accounting.money import ZERO, money, strings
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import require
from apps.audit.services import record
from apps.banking.models import BankAccount
from apps.core.exceptions import BusinessRuleViolation
from apps.sales.services import _get

from .models import CashFlowReview

CATEGORIES = ("operating", "investing", "financing", "opening_cutover", "unclassified")


def cash_movements(start, end):
    return (
        JournalEntry.objects.filter(
            status="posted",
            posting_date__range=(start, end),
            lines__account_id__in=BankAccount.objects.values("gl_account_id"),
        )
        .annotate(cash_debit=Sum("lines__base_debit"), cash_credit=Sum("lines__base_credit"))
        .order_by("posting_date", "number")
    )


def _automatic(journal):
    source = journal.reversal_of if journal.reversal_of_id else journal
    if source.kind == "opening" or source.source_type == "cutover":
        return "opening_cutover"
    if source.source_type in ("customer_payment", "customer_refund"):
        return "operating"
    if source.source_type == "founder_transaction" and journal.funding_kind in (
        "receipt",
        "loan_repayment",
    ):
        return "financing"
    if (
        source.source_type == "expense"
        and not journal.capitalized
        and journal.expense_account_type == "expense"
    ):
        return "operating"
    # Mixed vendor payments, reimbursements and manual adjustments require a
    # retained review. A bank movement alone cannot prove investing/financing.
    return "unclassified"


def classified_statement(out, start, end):
    """Called by accounting.reports.report('cf') while it holds the company lock."""
    from apps.accounting.money import decimal
    from apps.assets.models import Asset
    from apps.founders.models import CorporateTransaction
    from apps.purchasing.models import Expense

    totals = {category: ZERO for category in CATEGORIES}
    actual_receipts = actual_payments = ZERO
    journal_count = unclassified_count = 0
    movements = (
        cash_movements(start, end)
        .select_related("reversal_of")
        .annotate(
            original_id=Coalesce("reversal_of_id", "pk", output_field=UUIDField()),
            latest_review=Subquery(
                CashFlowReview.objects.filter(journal_id=OuterRef("pk"))
                .order_by("-version")
                .values("allocations")[:1]
            ),
            funding_kind=Subquery(
                CorporateTransaction.objects.filter(journal_id=OuterRef("original_id")).values(
                    "kind"
                )[:1]
            ),
            expense_account_type=Subquery(
                Expense.objects.filter(journal_id=OuterRef("original_id")).values(
                    "account__account_type"
                )[:1]
            ),
            capitalized=Exists(
                Asset.objects.filter(
                    source_line__journal_id=OuterRef("original_id"), recognition_date__lte=end
                )
            ),
        )
    )
    for journal in movements:
        if journal.kind == "transfer":
            continue
        net = (journal.cash_debit or ZERO) - (journal.cash_credit or ZERO)
        if not net:
            continue
        journal_count += 1
        review = journal.latest_review
        source_category = _automatic(journal)
        if source_category != "opening_cutover":
            actual_receipts += max(net, ZERO)
            actual_payments += max(-net, ZERO)
        if review:
            for allocation in review:
                totals[allocation["category"]] += decimal(allocation["amount"], signed=True)
            if any(a["category"] == "unclassified" for a in review):
                unclassified_count += 1
        else:
            category = source_category
            totals[category] += net
            unclassified_count += int(category == "unclassified")
    opening = decimal(out["opening"], signed=True)
    closing = decimal(out["closing"], signed=True)
    fx = decimal(out["transfer_fx_effect"], signed=True)
    out.update(
        **strings(totals),
        actual_receipts=str(actual_receipts),
        actual_payments=str(actual_payments),
        activity_count=journal_count,
        unclassified_count=unclassified_count,
        classified_difference=str(closing - opening - sum(totals.values(), ZERO) - fx),
        classification=(
            "Source-classified cash movements; unreviewed or mixed sources "
            "remain explicitly unclassified. Internal transfers are excluded "
            "and their FX effect is separate."
        ),
    )
    return out


@transaction.atomic
def classify(request, data):
    require(request.user, "finance.view", "reports.classify")
    company = lock_company()
    journal = _get(JournalEntry, data["journal_id"])
    if journal.status != "posted" or journal.kind == "transfer":
        raise BusinessRuleViolation(
            "Classify a posted external cash movement. Internal transfers are "
            "eliminated separately."
        )
    net = (
        JournalLine.objects.filter(
            journal=journal, account_id__in=BankAccount.objects.values("gl_account_id")
        ).aggregate(v=Sum(F("base_debit") - F("base_credit")))["v"]
        or ZERO
    )
    if not net:
        raise BusinessRuleViolation("This journal has no external cash movement.")
    allocations = []
    for part in data["allocations"]:
        if part["category"] not in CATEGORIES:
            raise ValidationError({"category": "Choose a supported cash-flow activity."})
        value = money(part["amount"], company.base_currency, signed=True)
        if not value:
            raise ValidationError({"amount": "Enter a nonzero signed amount for every allocation."})
        allocations.append({"category": part["category"], "amount": value})
    if sum((a["amount"] for a in allocations), ZERO) != net:
        raise BusinessRuleViolation(
            "Classified allocations must equal the exact posted net cash movement."
        )
    version = (journal.cash_flow_reviews.aggregate(v=Max("version"))["v"] or 0) + 1
    if data.get("expected_version", version - 1) != version - 1:
        raise BusinessRuleViolation(
            "The classification changed. Reload its retained review history."
        )
    obj = CashFlowReview.objects.create(
        journal=journal,
        version=version,
        allocations=strings(allocations),
        reason=data["reason"],
        created_by=request.user,
    )
    record(
        "reporting.cash_flow_classified",
        request=request,
        target=obj,
        after={
            "journal_id": journal.pk,
            "version": version,
            "allocations": allocations,
            "journal_changed": False,
        },
        reason=obj.reason,
    )
    return obj
