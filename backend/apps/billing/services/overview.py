"""Posted-ledger overview series. No stored balances or browser money calculations."""

from datetime import date

from django.db.models import F, Q, Sum
from django.db.models.functions import TruncMonth

from apps.accounting.models import JournalLine
from apps.accounting.money import ZERO

from ..models import Invoice


def fiscal_months(company, today):
    month = company.fiscal_year_start_month
    year = today.year - (today.month < month)
    start = date(year, month, 1)
    months = []
    current = start
    while current <= today:
        months.append(current.isoformat()[:7])
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    return start, months


def source_lines(sources, start, end):
    return JournalLine.objects.filter(
        Q(journal__source_type__in=sources)
        | Q(journal__source_type="reversal", journal__reversal_of__source_type__in=sources),
        journal__status="posted",
        journal__posting_date__gte=start,
        journal__posting_date__lte=end,
    )


def monthly(qs):
    rows = (
        qs.annotate(month=TruncMonth("journal__posting_date"))
        .values("month")
        .annotate(amount=Sum(F("base_debit") - F("base_credit")))
        .order_by()
    )
    return {row["month"].isoformat()[:7]: row["amount"] for row in rows}


def sales(company, today):
    start, months = fiscal_months(company, today)
    invoiced = monthly(
        source_lines(["invoice"], start, today).filter(account__control="receivable")
    )
    collected = monthly(
        source_lines(["customer_payment"], start, today).filter(account__bank_account__isnull=False)
    )
    aging = [
        {"label": label, "amount": ZERO, "count": 0}
        for label in ("Current", "1–30 days", "31–60 days", "61–90 days", "90+ days")
    ]
    for invoice in Invoice.objects.filter(
        status__in=("issued", "partially_paid"), issue_date__lte=today
    ):
        amount = invoice.base_total - invoice.base_settled
        days = (today - invoice.due_date).days
        index = 0 if days <= 0 else 1 if days <= 30 else 2 if days <= 60 else 3 if days <= 90 else 4
        aging[index]["amount"] += amount
        aging[index]["count"] += 1
    return {
        "series": [
            {"month": m, "invoiced": invoiced.get(m, ZERO), "collected": collected.get(m, ZERO)}
            for m in months
        ],
        "aging": aging,
        "series_from": start,
        "invoiced_this_month": invoiced.get(months[-1], ZERO),
        "collected_this_month": collected.get(months[-1], ZERO),
    }


def purchasing(company, today):
    start, months = fiscal_months(company, today)
    lines = source_lines(["vendor_bill", "expense"], start, today).filter(
        account__account_type="expense"
    )
    values = monthly(lines)
    accounts = list(
        lines.values("account_id", "account__code", "account__name")
        .annotate(amount=Sum(F("base_debit") - F("base_credit")))
        .order_by("-amount", "account__code")
    )
    top = accounts[:5]
    series = [{"key": f"a{a['account_id']}", "label": a["account__name"]} for a in top]
    if len(accounts) > 5:
        series.append({"key": "other", "label": "Other"})
    buckets = {
        m: {"month": m, "expense": values.get(m, ZERO), **{s["key"]: ZERO for s in series}}
        for m in months
    }
    known = {a["account_id"] for a in top}
    for row in (
        lines.annotate(month=TruncMonth("journal__posting_date"))
        .values("month", "account_id")
        .annotate(amount=Sum(F("base_debit") - F("base_credit")))
    ):
        key = f"a{row['account_id']}" if row["account_id"] in known else "other"
        buckets[row["month"].isoformat()[:7]][key] = (
            buckets[row["month"].isoformat()[:7]].get(key, ZERO) + row["amount"]
        )

    # Source records supply vendor identity; every value still comes from posted expense lines.
    from apps.purchasing.models import Expense, VendorBill

    vendors, journals = {}, {}
    for model in (VendorBill, Expense):
        for record in (
            model.objects.filter(journal__isnull=False, vendor__isnull=False)
            .select_related("vendor")
            .only("journal_id", "void_journal_id", "vendor__name", "vendor_id")
        ):
            vendors[record.vendor_id] = record.vendor.name
            journals[record.journal_id] = record.vendor_id
            if record.void_journal_id:
                journals[record.void_journal_id] = record.vendor_id
    spend = {}
    for row in lines.values("journal_id").annotate(amount=Sum(F("base_debit") - F("base_credit"))):
        vendor_id = journals.get(row["journal_id"])
        if vendor_id:
            spend[vendor_id] = spend.get(vendor_id, ZERO) + row["amount"]
    return {
        "series_from": start,
        "series": list(buckets.values()),
        "expense_series": series,
        "top_vendors": [
            {"label": vendors[pk], "amount": amount}
            for pk, amount in sorted(spend.items(), key=lambda x: x[1], reverse=True)[:8]
        ],
        "categories": [
            {"label": f"{a['account__code']} · {a['account__name']}", "amount": a["amount"]}
            for a in accounts
        ],
    }
