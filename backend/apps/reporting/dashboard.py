"""Permission-aware executive aggregates over the existing authoritative sources."""

from datetime import date, timedelta
from decimal import Decimal, localcontext

from django.db import transaction
from django.db.models import F, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.accounting import reports
from apps.accounting.models import JournalLine
from apps.accounting.money import ZERO, decimal, strings
from apps.accounts.authorization import get_permission_codes
from apps.assets.models import Asset, DepreciationCharge
from apps.banking.models import BankAccount
from apps.billing.models import Invoice
from apps.budgeting.models import Budget
from apps.budgeting.services import comparison
from apps.company.models import CompanyProfile
from apps.inventory.models import Movement
from apps.purchasing.models import PurchaseOrder

from .aging import aging


def _change(value, previous):
    if previous == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return ((value - previous) / abs(previous) * 100).quantize(Decimal("0.1"))


def series(start, end):
    qs = JournalLine.objects.filter(
        journal__status="posted", journal__posting_date__range=(start, end)
    )
    rows = (
        qs.annotate(month=TruncMonth("journal__posting_date"))
        .values("month")
        .annotate(
            revenue=Sum(
                F("base_credit") - F("base_debit"), filter=Q(account__account_type="revenue")
            ),
            expense=Sum(
                F("base_debit") - F("base_credit"), filter=Q(account__account_type="expense")
            ),
        )
        .order_by("month")
    )
    by_month = {row["month"].replace(day=1): row for row in rows}
    on = start.replace(day=1)
    result = []
    while on <= end:
        row = by_month.get(on, {})
        rev, exp = row.get("revenue") or ZERO, row.get("expense") or ZERO
        result.append(
            {"month": on.strftime("%Y-%m"), "revenue": rev, "expenses": exp, "profit": rev - exp}
        )
        on = date(on.year + (on.month == 12), on.month % 12 + 1, 1)
    return result


@transaction.atomic
def summary(user, start, end):
    company = CompanyProfile.objects.select_for_update().filter(pk=1).first()
    if company is None:
        return {
            "configured": False,
            "base_currency": None,
            "metrics": [],
            "series": [],
            "alerts": [],
            "from": start,
            "to": end,
        }
    codes = get_permission_codes(user)
    result = {
        "configured": True,
        "base_currency": company.base_currency,
        "from": start,
        "to": end,
        "metrics": [],
        "series": [],
        "alerts": [],
    }
    if "finance.view" not in codes:
        result["alerts"] = [
            {
                "tone": "info",
                "text": (
                    "Your role does not include financial KPIs. Use the navigation "
                    "for your authorized work."
                ),
                "route": None,
            }
        ]
        return strings(result)
    pnl = reports.report("pnl", start, end)
    cash = reports.report("cf", start, end)
    days = (end - start).days + 1
    prior_end = start - timedelta(days=1) if start > date.min else start
    prior_start = max(
        date(1, 1, 1), start - timedelta(days=min(days, (start - date(1, 1, 1)).days))
    )
    prior = reports.report("pnl", prior_start, prior_end) if prior_end >= prior_start else None
    # Cash-on-hand is NOT the bank + cash aggregate. Include every registered
    # cash account (even if subsequently deactivated) for historical accuracy.
    cash_account_ids = BankAccount.objects.filter(kind="cash").values_list(
        "gl_account_id", flat=True
    )
    cash_posted = JournalLine.objects.filter(
        journal__status="posted",
        journal__posting_date__lte=end,
        account_id__in=cash_account_ids,
    ).aggregate(debits=Sum("base_debit"), credits=Sum("base_credit"))
    cash_on_hand = (cash_posted["debits"] or ZERO) - (cash_posted["credits"] or ZERO)
    metrics = [
        {
            "key": "cash_on_hand",
            "label": "Current cash balance",
            "value": cash_on_hand,
            "kind": "money",
            "route": "/banking/accounts",
            "sub": f"Cash on hand · at {end} · excludes bank accounts",
        }
    ]
    for key, label, route in [
        ("revenue", "Revenue (accrual)", "/banking/statements/pnl"),
        ("expenses", "Total expenses", "/reports/expense"),
        ("net_profit", "Net profit / (loss)", "/banking/statements/pnl"),
    ]:
        value = decimal(pnl[key], signed=True)
        previous = decimal(prior[key], signed=True) if prior else ZERO
        metrics.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "kind": "money",
                "route": route,
                "sub": "Posted GL · selected period",
                "previous": previous,
                "change_percent": _change(value, previous),
            }
        )
    for key, label, source in [
        ("cash_received", "Cash received", "actual_receipts"),
        ("cash_paid", "Cash paid", "actual_payments"),
        ("cash", "Cash / bank position", "closing"),
    ]:
        metrics.append(
            {
                "key": key,
                "label": label,
                "value": cash[source],
                "kind": "money",
                "route": "/banking/transactions",
                "sub": "Transfers and opening/cutover excluded" if key != "cash" else f"At {end}",
            }
        )
    ar, ap = aging("ar", end), aging("ap", end)
    overdue = sum(
        (
            row["base_outstanding"]
            for row in ar["rows"]
            if row["days_overdue"] and row["days_overdue"] > 0
        ),
        ZERO,
    )
    for key, label, value, route in [
        ("ar", "Receivables", ar["ledger"], "/reports/ar"),
        ("overdue", "Overdue customer balances", overdue, "/reports/ar"),
        ("ap", "Payables", ap["ledger"], "/reports/ap"),
    ]:
        metrics.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "kind": "money",
                "route": route,
                "sub": f"Historical GL at {end}",
            }
        )
    stock = Movement.objects.filter(date__lte=end).aggregate(v=Sum("base_value"))["v"] or ZERO
    active = (
        Asset.objects.filter(recognition_date__lte=end)
        .filter(Q(disposal__isnull=True) | Q(disposal__date__gt=end))
        .filter(Q(cancellation__isnull=True) | Q(cancellation__date__gt=end))
    )
    asset_cost = active.aggregate(v=Sum("cost"))["v"] or ZERO
    depreciation = (
        DepreciationCharge.objects.filter(
            asset_id__in=active.values("pk"), recognition_date__lte=end
        ).aggregate(v=Sum("amount"))["v"]
        or ZERO
    )
    metrics.extend(
        [
            {
                "key": "inventory",
                "label": "Inventory value",
                "value": stock,
                "kind": "money",
                "route": "/inventory/valuation",
                "sub": f"Historical stock events at {end}",
            },
            {
                "key": "assets",
                "label": "Active asset book value",
                "value": asset_cost - depreciation,
                "kind": "money",
                "route": "/assets/register",
                "sub": "Actual posted depreciation only",
            },
        ]
    )
    if end >= timezone.localdate():
        metrics.extend(
            [
                {
                    "key": "pending_invoices",
                    "label": "Pending invoices",
                    "value": Invoice.objects.filter(
                        status__in=["draft", "pending_approval", "approved"]
                    ).count(),
                    "kind": "count",
                    "route": "/sales/invoices",
                    "sub": "Current workflow state · no posted revenue",
                },
                {
                    "key": "pending_orders",
                    "label": "Open purchase orders",
                    "value": PurchaseOrder.objects.filter(
                        status__in=["pending", "approved", "issued", "partial"]
                    ).count(),
                    "kind": "count",
                    "route": "/purchases/orders",
                    "sub": "Current commitments · not payables",
                },
            ]
        )
    planned = actual = ZERO
    for budget in Budget.objects.filter(
        is_archived=False, active_revision__isnull=False
    ).select_related("active_revision"):
        for row in comparison(budget.active_revision):
            month = date.fromisoformat(row["month"])
            if start.replace(day=1) <= month <= end:
                planned += decimal(row["revised"])
                actual += decimal(row["actual"], signed=True)
    if planned:
        metrics.append(
            {
                "key": "budget",
                "label": "Budget utilization",
                "value": (actual / planned * 100).quantize(Decimal("0.1")),
                "kind": "percent",
                "route": "/budgets/comparison",
                "sub": "Current approved allocations · selected months",
            }
        )
    if overdue > 0:
        result["alerts"].append(
            {
                "tone": "warn",
                "text": "Customer balances are overdue at the selected date.",
                "route": "/reports/ar",
            }
        )
    if ar["unallocated"] or ap["unallocated"]:
        result["alerts"].append(
            {
                "tone": "warn",
                "text": (
                    "Unallocated or opening control balances require source review; "
                    "aging discloses them separately."
                ),
                "route": "/reports/ar",
            }
        )
    if cash["unclassified_count"]:
        result["alerts"].append(
            {
                "tone": "warn",
                "text": "Some cash movements require a retained activity classification.",
                "route": "/reports/cash-flow",
            }
        )
    if actual > planned and planned:
        result["alerts"].append(
            {
                "tone": "warn",
                "text": "Posted spending exceeds the selected approved budget allocations.",
                "route": "/budgets/comparison",
            }
        )
    result.update(
        metrics=metrics,
        series=series(start, end),
        aging={"receivable": ar["buckets"], "payable": ap["buckets"]},
        cash_flow=cash,
        definitions={
            "recognized": (
                "Posted general ledger only. Invoices, stock control, expenses "
                "and adjustments retain source-owned recognition."
            ),
            "plans": (
                "Budgets and funding forecasts are separate from actuals; current "
                "approved budget scopes are used."
            ),
            "workflow": (
                "Pending document counts show current workflow state, only for a "
                "range reaching today."
            ),
        },
    )
    return strings(result)
