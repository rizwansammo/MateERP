"""Read-only source balances reconciled independently with posted GL controls."""

from django.db import transaction
from django.db.models import F, Sum

from apps.accounting.models import Account, JournalLine
from apps.accounting.money import ZERO, strings
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import require
from apps.company.models import FinancialParty
from apps.core.exceptions import BusinessRuleViolation
from apps.ownership.models import OwnershipProposal, ShareClass

from ..models import CorporateTransaction, FounderObligation, PersonalObligation
from .common import on_date
from .corporate import CONTROLS, outstanding
from .sharing import settled


def obligation_row(obj):
    native, base = outstanding(obj)
    return strings(
        {
            "id": obj.pk,
            "party_id": obj.party_id,
            "party": str(obj.party),
            "category": obj.category,
            "currency": obj.currency,
            "amount": obj.amount,
            "base_amount": obj.base_amount,
            "outstanding": native,
            "base_outstanding": base,
            "origin_id": obj.origin_id,
            "expense_id": obj.original_expense_id,
        }
    )


@transaction.atomic
def reconciliation(request):
    require(request.user, "founder.view")
    lock_company()
    rows = []
    for category, purpose in CONTROLS.items():
        purposes = [purpose, "share_premium"] if category == "share_capital" else [purpose]
        if category in {"payable", "loan", "pending"}:
            expected = sum(
                (
                    outstanding(o)[1]
                    for o in FounderObligation.objects.filter(
                        category=category, origin__status="posted"
                    )
                ),
                ZERO,
            )
        else:
            expected = ZERO
            for tx in CorporateTransaction.objects.filter(status="posted"):
                for line in tx.snapshot.get("quote", {}).get("lines", []):
                    if Account.objects.filter(pk=line["account_id"], control__in=purposes).exists():
                        from decimal import Decimal

                        expected += Decimal(line["base_credit"]) - Decimal(line["base_debit"])
        actual = (
            JournalLine.objects.filter(
                account__control__in=purposes, journal__status="posted"
            ).aggregate(value=Sum(F("base_credit") - F("base_debit")))["value"]
            or ZERO
        )
        rows.append(
            {
                "category": category,
                "controls": purposes,
                "source_balance": expected,
                "gl_balance": actual,
                "difference": actual - expected,
            }
        )
    return strings(rows)


@transaction.atomic
def overview(request, party_id=None):
    require(request.user, "founder.view")
    lock_company()
    parties = FinancialParty.objects.filter(is_founder=True)
    if party_id:
        parties = parties.filter(pk=party_id)
    rows = []
    for participant in parties:
        liabilities = [
            obligation_row(o) for o in participant.obligations.filter(origin__status="posted")
        ]
        events = participant.corporate_transactions.select_related("journal").order_by(
            "-date", "-pk"
        )
        rows.append(
            {
                "id": participant.pk,
                "name": str(participant),
                "is_active": participant.is_active,
                "obligations": liabilities,
                "events": [
                    {
                        "id": e.pk,
                        "kind": e.kind,
                        "classification": e.classification,
                        "date": e.date,
                        "currency": e.currency,
                        "amount": e.amount,
                        "status": e.status,
                        "journal_id": e.journal_id,
                        "journal_number": e.journal.number if e.journal else None,
                    }
                    for e in events[:100]
                ],
            }
        )
    from django.utils import timezone

    year = timezone.localdate().year
    monthly = {
        month: {
            "month": f"{year}-{month:02}",
            "receipts": ZERO,
            "funded_costs": ZERO,
            "repayments": ZERO,
        }
        for month in range(1, 13)
    }
    events = CorporateTransaction.objects.filter(status__in=["posted", "reversed"])
    if party_id:
        events = events.filter(party_id=party_id)
    for event in events.select_related("reversal_journal"):
        series = (
            "receipts"
            if event.kind == "receipt"
            else "funded_costs"
            if event.kind in {"expense", "vendor_payment"}
            else "repayments"
            if event.kind in {"reimbursement", "loan_repayment"}
            else None
        )
        if series and event.date.year == year:
            monthly[event.date.month][series] += event.base_amount
        if (
            series
            and event.reversal_journal_id
            and event.reversal_journal.posting_date.year == year
        ):
            monthly[event.reversal_journal.posting_date.month][series] -= event.base_amount
    return strings(
        {
            "founders": rows,
            "reconciliation": reconciliation(request),
            "monthly": list(monthly.values()),
        }
    )


@transaction.atomic
def statement(request):
    """Credit-normal corporate control movements, including source reversals.

    Source-owned journal dimensions identify the party even for a reassignment.
    Opening balances are actual preceding postings, never inferred from cash
    contributions or personal settlements.
    """
    require(request.user, "founder.view")
    lock_company()
    params = request.query_params
    start = on_date(params["from"]) if params.get("from") else None
    end = on_date(params["to"]) if params.get("to") else None
    if start and end and end < start:
        raise BusinessRuleViolation("The statement end date precedes its start.")
    lines = (
        JournalLine.objects.filter(
            journal__status="posted",
            account__control__in=[*CONTROLS.values(), "share_premium"],
            dimensions__has_key="founder",
        )
        .select_related("journal", "account")
        .order_by("journal__posting_date", "journal__number", "position")
    )
    if params.get("party_id"):
        from rest_framework.serializers import IntegerField

        pk = IntegerField(min_value=1).run_validation(params["party_id"])
        lines = lines.filter(dimensions__founder=pk)
    if end:
        lines = lines.filter(journal__posting_date__lte=end)
    names = {p.pk: str(p) for p in FinancialParty.objects.all()}
    balances, base_balances, rows = {}, {}, []
    for line in lines:
        party_id = int(line.dimensions["founder"])
        key = f"{party_id}:{line.account.control}:{line.currency}"
        balances[key] = balances.get(key, ZERO) + line.credit - line.debit
        base_balances[key] = base_balances.get(key, ZERO) + line.base_credit - line.base_debit
        if start and line.journal.posting_date < start:
            continue
        rows.append(
            {
                "id": line.pk,
                "date": line.journal.posting_date,
                "party_id": party_id,
                "party": names.get(party_id, str(party_id)),
                "control": line.account.control,
                "currency": line.currency,
                "debit": line.debit,
                "credit": line.credit,
                "balance": balances[key],
                "base_balance": base_balances[key],
                "journal": line.journal_id,
                "number": line.journal.number,
                "description": line.journal.description,
            }
        )
    return strings(rows)


def personal_balance_rows(user):
    from django.db.models import Q

    from apps.accounts.authorization import get_permission_codes

    qs = PersonalObligation.objects.select_related("sharing", "debtor", "creditor")
    if "founder.attest" not in get_permission_codes(user):
        qs = qs.filter(Q(debtor__user=user) | Q(creditor__user=user))
    return strings(
        [
            {
                "id": o.pk,
                "sharing_id": o.sharing_id,
                "debtor_id": o.debtor_id,
                "creditor_id": o.creditor_id,
                "debtor": str(o.debtor),
                "creditor": str(o.creditor),
                "currency": o.sharing.currency,
                "date": o.sharing.date,
                "description": o.sharing.description,
                "amount": o.amount,
                "settled": settled(o),
                "outstanding": o.amount - settled(o),
            }
            for o in qs.order_by("-sharing__date", "-pk")
        ]
    )


@transaction.atomic
def capital(request):
    require(request.user, "ownership.view")
    lock_company()
    from django.utils import timezone

    from apps.ownership.services.register import holdings, provisional

    on = on_date(getattr(request, "query_params", {}).get("date", timezone.localdate()))
    classes = []
    current = holdings(on)
    for cls in ShareClass.objects.all():
        register = current.get(str(cls.pk), {"units": {}, "percentages": {}, "total": 0})
        confirmed = OwnershipProposal.objects.filter(
            share_class=cls,
            status="confirmed",
            kind__in=["issuance", "opening"],
            effective_date__lte=on,
        )
        subscribed = sum(
            (line.price * line.units for p in confirmed for line in p.lines.all()), ZERO
        )
        paid = sum(
            (
                tx.amount
                for tx in CorporateTransaction.objects.filter(
                    issuance__in=confirmed,
                    classification="share_capital",
                    status="posted",
                    date__lte=on,
                )
            ),
            ZERO,
        )
        classes.append(
            {
                "id": cls.pk,
                "name": cls.name,
                "currency": cls.currency,
                "par_value": cls.par_value,
                "rights": cls.rights,
                "register": register,
                "subscribed": subscribed,
                "paid_in": paid,
                "unpaid_commitments": max(ZERO, subscribed - paid),
                "nominal": cls.par_value * register["total"] if cls.par_value is not None else None,
            }
        )
    return strings(
        {
            "classes": classes,
            "provisional": provisional(on),
            "date": on,
            "note": "Agreement percentages, issued units and paid-in capital are distinct. "
            "Unpaid commitments do not record company cash.",
        }
    )
