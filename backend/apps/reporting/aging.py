"""As-of aging uses immutable control-account lines, including dated reversals.

Current cached document settlements are intentionally not used for past dates.
Unallocated conversion/legacy control balances are disclosed and reconcile exactly.
"""

from django.db.models import F, Sum

from apps.accounting.models import JournalLine
from apps.accounting.money import ZERO
from apps.billing.models import Invoice
from apps.purchasing.models import Expense, VendorBill


def aging(which, end):
    receivable = which == "ar"
    control = "receivable" if receivable else "payable"
    query = JournalLine.objects.filter(
        journal__status="posted", journal__posting_date__lte=end, account__control=control
    )
    rows = query.values("dimensions").annotate(value=Sum(F("base_debit") - F("base_credit")))
    balances = {}
    unallocated = ZERO
    for row in rows:
        dims = row["dimensions"]
        value = row["value"] if receivable else -row["value"]
        if not value:
            continue
        kind = "invoice" if receivable else "bill" if dims.get("bill") else "expense"
        pk = dims.get(kind)
        if isinstance(pk, int) or isinstance(pk, str) and pk.isdecimal():
            key = (kind, int(pk))
            balances[key] = balances.get(key, ZERO) + value
        else:
            unallocated += value
    sources = {}
    for kind, model, relation in (
        (("invoice", Invoice, "customer"),)
        if receivable
        else (("bill", VendorBill, "vendor"), ("expense", Expense, "vendor"))
    ):
        ids = [key[1] for key in balances if key[0] == kind]
        for obj in model.objects.filter(pk__in=ids).select_related(relation):
            sources[(kind, obj.pk)] = obj
    result = []
    for key, value in balances.items():
        if not value:
            continue
        obj = sources.get(key)
        if obj is None or obj.due_date is None:
            unallocated += value
            continue
        days = (end - obj.due_date).days
        bucket = (
            "current"
            if days <= 0
            else "1_30"
            if days <= 30
            else "31_60"
            if days <= 60
            else "61_90"
            if days <= 90
            else "90_plus"
        )
        party = obj.customer if receivable else obj.vendor
        result.append(
            {
                "kind": key[0],
                "id": obj.pk,
                "number": obj.number,
                "party_id": party.pk if party else None,
                "party": party.name if party else "Unspecified",
                "due_date": obj.due_date,
                "days_overdue": max(0, days),
                "bucket": bucket,
                "base_outstanding": value,
                "route": f"/sales/invoices/{obj.pk}"
                if receivable
                else f"/purchases/{'bills' if key[0] == 'bill' else 'expenses'}/{obj.pk}",
            }
        )
    if unallocated:
        result.append(
            {
                "kind": "unallocated",
                "id": None,
                "number": "Unallocated / opening control balance",
                "party_id": None,
                "party": "Review retained conversion or source evidence",
                "due_date": None,
                "days_overdue": None,
                "bucket": "unallocated",
                "base_outstanding": unallocated,
                "route": "/banking/accounts",
            }
        )
    total = query.aggregate(v=Sum(F("base_debit") - F("base_credit")))["v"] or ZERO
    total = total if receivable else -total
    buckets = {key: ZERO for key in ("current", "1_30", "31_60", "61_90", "90_plus", "unallocated")}
    for row in result:
        buckets[row["bucket"]] += row["base_outstanding"]
    return {
        "rows": sorted(result, key=lambda r: (r["due_date"] or end, r["number"] or "")),
        "ledger": total,
        "aged_total": sum(buckets.values(), ZERO),
        "difference": total - sum(buckets.values(), ZERO),
        "buckets": buckets,
        "unallocated": unallocated,
        "as_of": end,
    }
