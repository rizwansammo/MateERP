"""Read-only purchasing queries used by other modules."""

from django.db.models import F, Sum

from apps.accounting.models import JournalLine
from apps.accounting.money import ZERO


def project_costs(project):
    """Posted expense costs, retaining source currency and historical GL base valuation.

    Capitalized assets and recoverable input tax are not project expenses.
    ``total`` is the project-currency subset for compatibility; ``base_total``
    includes every currency and is the authoritative profitability measure.
    """
    from ..models import Expense, VendorBill

    lines, total, base_total = [], ZERO, ZERO
    for bill in VendorBill.objects.filter(
        project=project, status__in=VendorBill.POSTED_STATES
    ).select_related("vendor"):
        amount = (
            bill.lines.filter(account__account_type="expense").aggregate(value=Sum("taxable"))[
                "value"
            ]
            or ZERO
        )
        base = (
            JournalLine.objects.filter(
                journal_id=bill.journal_id, account__account_type="expense"
            ).aggregate(value=Sum(F("base_debit") - F("base_credit")))["value"]
            or ZERO
        )
        if amount:
            lines.append(
                {
                    "kind": "Vendor bill",
                    "id": bill.pk,
                    "number": bill.number,
                    "date": bill.bill_date,
                    "party": bill.vendor.name,
                    "amount": amount,
                    "currency": bill.currency,
                    "base_amount": base,
                }
            )
            base_total += base
            if bill.currency == project.currency:
                total += amount
    for exp in Expense.objects.filter(
        project=project, status__in=("posted", "partially_paid", "paid")
    ).select_related("vendor", "account"):
        if exp.account.account_type == "expense":
            base = (
                JournalLine.objects.filter(
                    journal_id=exp.journal_id, account__account_type="expense"
                ).aggregate(value=Sum(F("base_debit") - F("base_credit")))["value"]
                or ZERO
            )
            lines.append(
                {
                    "kind": "Expense",
                    "id": exp.pk,
                    "number": exp.number,
                    "date": exp.expense_date,
                    "party": exp.vendor.name if exp.vendor else "",
                    "amount": exp.taxable,
                    "currency": exp.currency,
                    "base_amount": base,
                }
            )
            base_total += base
            if exp.currency == project.currency:
                total += exp.taxable
    return {
        "lines": sorted(lines, key=lambda x: x["date"]),
        "total": total,
        "base_total": base_total,
    }
