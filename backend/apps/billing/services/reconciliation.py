"""Receivable and customer-credit subledgers reconciled to their GL control accounts.

Subledger balances are computed from the business documents' own base snapshots
(issued base total minus base settled; customer-credit movements), independently of
journal lines. The difference to the control account must be exactly zero.
"""

from django.db.models import F, Sum
from django.utils import timezone

from apps.accounting.models import Account, JournalLine
from apps.accounting.money import ZERO

from ..models import CustomerCreditMovement, Invoice

OPEN = ("issued", "partially_paid")


def gl_balance(control: str, *, credit_normal: bool):
    account = Account.objects.filter(control=control).first()
    if account is None:
        return None, ZERO
    agg = JournalLine.objects.filter(account=account, journal__status="posted").aggregate(
        d=Sum("base_debit"), c=Sum("base_credit")
    )
    debit, credit = agg["d"] or ZERO, agg["c"] or ZERO
    return account, (credit - debit) if credit_normal else (debit - credit)


def receivables():
    issued = Invoice.objects.filter(number__isnull=False).exclude(status="void")
    sub = issued.aggregate(t=Sum("base_total"), s=Sum("base_settled"))
    subledger = (sub["t"] or ZERO) - (sub["s"] or ZERO)
    account, gl = gl_balance("receivable", credit_normal=False)
    credit_sub = CustomerCreditMovement.objects.aggregate(b=Sum("base_amount"))["b"] or ZERO
    credit_account, credit_gl = gl_balance("customer_credit", credit_normal=True)
    return {
        "receivable": {
            "account": account,
            "subledger": subledger,
            "ledger": gl,
            "difference": gl - subledger,
        },
        "customer_credit": {
            "account": credit_account,
            "subledger": credit_sub,
            "ledger": credit_gl,
            "difference": credit_gl - credit_sub,
        },
    }


def customer_balances(customer_ids=None):
    """Open native balances per customer and currency, with overdue amounts."""
    today = timezone.localdate()
    qs = Invoice.objects.filter(status__in=OPEN)
    if customer_ids is not None:
        qs = qs.filter(customer_id__in=customer_ids)
    out = {}
    rows = (
        qs.values("customer_id", "currency")
        .annotate(open=Sum(F("total") - F("amount_paid") - F("amount_credited")))
        .order_by()
    )
    for row in rows:
        out.setdefault(row["customer_id"], {})[row["currency"]] = {
            "outstanding": row["open"],
            "overdue": ZERO,
        }
    overdue = (
        qs.filter(due_date__lt=today)
        .values("customer_id", "currency")
        .annotate(open=Sum(F("total") - F("amount_paid") - F("amount_credited")))
        .order_by()
    )
    for row in overdue:
        out[row["customer_id"]][row["currency"]]["overdue"] = row["open"]
    credits = (
        CustomerCreditMovement.objects.filter(
            **({"customer_id__in": customer_ids} if customer_ids is not None else {})
        )
        .values("customer_id", "currency")
        .annotate(n=Sum("amount"))
        .order_by()
    )
    for row in credits:
        if row["n"]:
            entry = out.setdefault(row["customer_id"], {}).setdefault(
                row["currency"], {"outstanding": ZERO, "overdue": ZERO}
            )
            entry["credit"] = row["n"]
    return out
