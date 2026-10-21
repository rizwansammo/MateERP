"""Source-owned project attribution over posted GL; no financial allocations are invented."""

from django.db.models import F, Q, Sum

from apps.accounting.models import JournalLine
from apps.accounting.money import ZERO
from apps.assets.models import Asset, AssetDisposal, CapitalizationReversal, DepreciationCharge
from apps.billing.models import ControlTransfer, CreditNote, CustomerReturn, Invoice
from apps.founders.models import CorporateTransaction
from apps.purchasing.models import Expense, VendorBill


def project_lines(project):
    invoices = Invoice.objects.filter(project=project)
    expenses = Expense.objects.filter(project=project)
    bills = VendorBill.objects.filter(project=project)
    acquisitions = Q(source_line__journal_id__in=expenses.values("journal_id")) | Q(
        source_line__journal_id__in=bills.values("journal_id")
    )
    assets = Asset.objects.filter(acquisitions)
    controls = ControlTransfer.objects.filter(policy__snapshot__project_id=project.pk)
    returns = CustomerReturn.objects.filter(transfer__policy__snapshot__project_id=project.pk)
    linked = (
        Q(journal_id__in=invoices.values("journal_id"))
        | Q(journal_id__in=invoices.values("void_journal_id"))
        | Q(journal_id__in=CreditNote.objects.filter(invoice__project=project).values("journal_id"))
        | Q(journal_id__in=expenses.values("journal_id"))
        | Q(journal_id__in=expenses.values("void_journal_id"))
        | Q(
            journal_id__in=CorporateTransaction.objects.filter(expense__project=project).values(
                "reversal_journal_id"
            )
        )
        | Q(journal_id__in=bills.values("journal_id"))
        | Q(journal_id__in=bills.values("void_journal_id"))
        | Q(journal_id__in=controls.values("journal_id"))
        | Q(journal_id__in=returns.values("movement__journal_id"))
        | Q(journal_id__in=assets.values("journal_id"))
        | Q(
            journal_id__in=CapitalizationReversal.objects.filter(
                asset_id__in=assets.values("pk")
            ).values("journal_id")
        )
        | Q(
            journal_id__in=DepreciationCharge.objects.filter(
                asset_id__in=assets.values("pk")
            ).values("journal_id")
        )
        | Q(
            journal_id__in=AssetDisposal.objects.filter(asset_id__in=assets.values("pk")).values(
                "journal_id"
            )
        )
        | Q(
            journal_id__in=AssetDisposal.objects.filter(asset_id__in=assets.values("pk")).values(
                "invoice_line__invoice__journal_id"
            )
        )
        | Q(dimensions__project=project.pk)
        | Q(dimensions__project=str(project.pk))
    )
    return JournalLine.objects.filter(linked, journal__status="posted")


def project_revenue(project):
    qs = project_lines(project).filter(account__account_type="revenue")
    base = qs.aggregate(v=Sum(F("base_credit") - F("base_debit")))["v"] or ZERO
    native_by_currency = {
        row["currency"]: row["value"]
        for row in qs.values("currency").annotate(value=Sum(F("credit") - F("debit")))
        if row["value"]
    }
    native = (
        None
        if any(c != project.currency for c in native_by_currency)
        else native_by_currency.get(project.currency, ZERO)
    )
    return base, native


def project_costs(project):
    qs = project_lines(project).filter(account__account_type="expense")
    base = qs.aggregate(v=Sum(F("base_debit") - F("base_credit")))["v"] or ZERO
    grouped = (
        qs.values("journal_id", "journal__number", "journal__posting_date", "currency")
        .annotate(
            amount=Sum(F("debit") - F("credit")),
            base_amount=Sum(F("base_debit") - F("base_credit")),
        )
        .order_by("journal__posting_date", "journal__number", "currency")
    )
    native_by_currency = {}
    lines = []
    for row in grouped:
        if not row["amount"] and not row["base_amount"]:
            continue
        native_by_currency[row["currency"]] = (
            native_by_currency.get(row["currency"], ZERO) + row["amount"]
        )
        lines.append(
            {
                "kind": "Posted journal",
                "id": str(row["journal_id"]),
                "number": row["journal__number"],
                "date": row["journal__posting_date"],
                "party": "",
                "currency": row["currency"],
                "amount": row["amount"],
                "base_amount": row["base_amount"],
                "route": f"/banking/journals/{row['journal_id']}",
            }
        )
    native = (
        None
        if any(
            currency != project.currency and value != 0
            for currency, value in native_by_currency.items()
        )
        else native_by_currency.get(project.currency, ZERO)
    )
    return {"base_total": base, "total": native, "lines": lines}
