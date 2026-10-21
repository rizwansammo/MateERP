"""Founder company transactions use the sole accounting engine and exact source allocations."""

from decimal import ROUND_HALF_UP, Decimal, localcontext

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounting.models import Account
from apps.accounting.money import ZERO, convert, strings
from apps.accounting.services import posting
from apps.accounting.services.adapters import authorize
from apps.accounting.services.setup import lock_company, rate_for
from apps.accounts.authorization import require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.banking.models import BankAccount
from apps.billing.services.common import settlement_base
from apps.company.services import next_number
from apps.core.exceptions import BusinessRuleViolation
from apps.purchasing.models import Expense, VendorBill
from apps.purchasing.services.payables import _debits, save_expense
from apps.sales.services import enabled_currency

from ..models import CorporateTransaction as Tx
from ..models import (
    FounderLoan,
    FounderObligation,
    FounderVendorAllocation,
    ObligationAllocation,
    PersonalAllocation,
    RecoveryResolution,
)
from .common import enabled, on_date, party, positive, total

CONTROLS = {
    "payable": "founder_payable",
    "loan": "founder_loan",
    "pending": "founder_pending",
    "other_equity": "founder_equity",
    "share_capital": "share_capital",
}
PAYOUTS = {"reimbursement", "loan_repayment", "reclassify", "reassign"}


def control(name):
    account = Account.objects.filter(control=name, is_active=True, is_postable=True).first()
    if not account:
        raise BusinessRuleViolation(
            f"Configure an unused, correctly typed {name.replace('_', ' ')} "
            "control account in Chart of Accounts.",
            code="founder_control_required",
        )
    return account


def outstanding(obligation):
    allocations = obligation.allocations.filter(transaction__status="posted")
    return obligation.amount - total(allocations), obligation.base_amount - total(
        allocations, "base_amount"
    )


@transaction.atomic
def save_loan(request, data):
    enabled()
    require(request.user, "founder.transactions.manage")
    lock_company()
    participant = party(data["party_id"], founder=True)
    enabled_currency(data["currency"])
    obj = FounderLoan(
        party=participant,
        created_by=request.user,
        **{k: data[k] for k in ("name", "currency", "terms", "maturity", "reference") if k in data},
    )
    obj.full_clean()
    obj.save()
    record(
        "founder.loan_created",
        request=request,
        target=obj,
        after={"party": participant.pk, "currency": obj.currency},
    )
    return obj


def _key(key):
    if not isinstance(key, str) or not 8 <= len(key) <= 160:
        raise ValidationError({"client_key": "Supply a stable operation key of 8–160 characters."})


@transaction.atomic
def record_transaction(request, data, key, *, historical_treatment=None):
    enabled()
    require(request.user, "founder.transactions.manage")
    lock_company()
    _key(key)
    from apps.accounting.models import HistoricalRecord

    historical = HistoricalRecord.objects.filter(
        external_reference=data.get("reference", "").strip().upper()
    ).first()
    if historical and not historical_treatment:
        raise BusinessRuleViolation(
            "This reference belongs to documented historical evidence. Use "
            "its independently reviewed treatment to prevent duplicate "
            "recognition."
        )
    identity = posting.fingerprint(strings(data))
    existing = Tx.objects.filter(client_key=key).first()
    if existing:
        if existing.fingerprint != identity:
            raise BusinessRuleViolation(
                "This key belongs to a different transaction.", code="idempotency_conflict"
            )
        return existing
    on = on_date(data["date"])
    participant = party(data["party_id"], on=on)
    if not (participant.is_founder or participant.is_shareholder):
        raise ValidationError(
            {"party_id": "Select a founder or shareholder financial participant."}
        )
    kind, classification = data["kind"], data["classification"]
    if (
        kind not in {"receipt", "expense", "vendor_payment"} | PAYOUTS
        or classification not in CONTROLS
    ):
        raise ValidationError({"kind": "Choose a supported transaction and classification."})
    if kind in PAYOUTS:
        require(request.user, "founder.liabilities.manage")
    currency = data["currency"]
    enabled_currency(currency)
    expense = None
    if kind == "expense":
        require(request.user, "expenses.manage")
        payload = {
            **data.get("expense", {}),
            "currency": currency,
            "expense_date": on,
            "payment_mode": "founder",
        }
        expense = save_expense(request, payload, historical_treatment=historical_treatment)
        value = expense.total
    else:
        value = positive(data["amount"], currency)
    obj = Tx(
        kind=kind,
        classification=classification,
        party=participant,
        date=on,
        currency=currency,
        amount=value,
        bank_id=data.get("bank_id"),
        loan_id=data.get("loan_id"),
        recipient_id=data.get("recipient_id"),
        issuance_id=data.get("issuance_id"),
        expense=expense,
        reference=data.get("reference", "").strip(),
        notes=data.get("notes", ""),
        client_key=key,
        fingerprint=identity,
        request_data=strings(data),
        created_by=request.user,
    )
    obj.full_clean()
    obj.save()
    # Validate the economic source now; current rates/availability are rechecked
    # independently at verification and when an approval executes.
    build(obj)
    record(
        "founder.transaction_recorded",
        request=request,
        target=obj,
        after={"kind": kind, "party": participant.pk, "amount": value, "currency": currency},
    )
    return obj


def _liability_rows(obj, company):
    raw, portions = [], []
    rows = obj.request_data.get("allocations") or []
    if not rows or len(rows) > 100:
        raise ValidationError({"allocations": "Select outstanding company obligations."})
    seen = set()
    for row in rows:
        pk = row["obligation_id"]
        if pk in seen:
            raise ValidationError({"allocations": "Allocate to each obligation once."})
        seen.add(pk)
        obligation = (
            FounderObligation.objects.select_for_update()
            .select_related("origin")
            .filter(pk=pk)
            .first()
        )
        if (
            not obligation
            or obligation.party_id != obj.party_id
            or obligation.currency != obj.currency
            or obligation.origin.status != "posted"
        ):
            raise ValidationError(
                {"allocations": "Select posted obligations for this founder and currency."}
            )
        expected = (
            "payable"
            if obj.kind == "reimbursement"
            else "loan"
            if obj.kind == "loan_repayment"
            else None
        )
        if expected and obligation.category != expected:
            raise ValidationError(
                {"allocations": f"This action only settles {expected} obligations."}
            )
        native, base = outstanding(obligation)
        value = positive(row["amount"], obj.currency)
        if value > native:
            raise BusinessRuleViolation(
                "The allocation exceeds the remaining company liability.", code="overallocation"
            )
        with localcontext() as context:
            context.prec = 60
            original_rate = obligation.base_amount / obligation.amount
        portion = settlement_base(
            value,
            total=obligation.amount,
            base_total=obligation.base_amount,
            native_settled=obligation.amount - native,
            base_settled=obligation.base_amount - base,
            rate=original_rate,
            base=company.base_currency,
        )
        raw.append(
            {
                "account_id": control(CONTROLS[obligation.category]).pk,
                "currency": obj.currency,
                "debit": str(value),
                "base_debit": str(portion),
                "exchange_rate": str(original_rate.quantize(Decimal("0.000000000001"))),
                "rate_source": "Original founder obligation carrying value",
                "valuation": "historical",
                "dimensions": {"founder": obj.party_id, "obligation": obligation.pk},
            }
        )
        portions.append((obligation, value, portion))
    if sum((r[1] for r in portions), ZERO) != obj.amount:
        raise ValidationError({"allocations": "Allocate the full amount exactly."})
    if obj.kind in {"reclassify", "reassign"} and len(portions) != 1:
        raise ValidationError(
            {
                "allocations": "Reclassify or reassign one original obligation per transaction "
                "to preserve its recovery history."
            }
        )
    if obj.kind in {"reimbursement", "loan_repayment"}:
        proposed = {}
        for obligation, value, _base in portions:
            root = obligation.recovery_origin_id or obligation.origin_id
            representative, subtotal = proposed.get(root, (obligation, ZERO))
            proposed[root] = representative, subtotal + value
        for obligation, value in proposed.values():
            assert_recovery_safe(obligation, value)
    return raw, portions


def _vendor_rows(obj, company):
    raw, portions, seen = [], [], set()
    rows = obj.request_data.get("vendor_allocations") or []
    if not rows or len(rows) > 100:
        raise ValidationError(
            {"vendor_allocations": "Select posted vendor bills or accrued expenses."}
        )
    for row in rows:
        kind = "bill" if row.get("bill_id") else "expense"
        pk = row.get("bill_id") or row.get("expense_id")
        if (kind, pk) in seen or bool(row.get("bill_id")) == bool(row.get("expense_id")):
            raise ValidationError({"vendor_allocations": "Select each source once."})
        seen.add((kind, pk))
        source = (
            (VendorBill if kind == "bill" else Expense)
            .objects.select_for_update()
            .filter(pk=pk)
            .first()
        )
        if (
            not source
            or source.currency != obj.currency
            or source.status not in ("posted", "partially_paid")
            or (kind == "expense" and source.payment_mode != "accrued")
        ):
            raise ValidationError(
                {"vendor_allocations": "Select open posted sources in the settlement currency."}
            )
        value = positive(row["amount"], obj.currency)
        portion = settlement_base(
            value,
            total=source.total,
            base_total=source.base_total,
            native_settled=source.amount_paid,
            base_settled=source.base_settled,
            rate=source.exchange_rate,
            base=company.base_currency,
        )
        raw.append(
            {
                "account_id": control("payable").pk,
                "currency": obj.currency,
                "debit": str(value),
                "base_debit": str(portion),
                "exchange_rate": str(source.exchange_rate),
                "rate_source": f"Original {source.number}",
                "valuation": "historical",
                "dimensions": {
                    "vendor": source.vendor_id,
                    kind: source.pk,
                    "founder": obj.party_id,
                },
            }
        )
        portions.append((kind, source, value, portion))
    if sum((r[2] for r in portions), ZERO) != obj.amount:
        raise ValidationError({"vendor_allocations": "Allocate the full payment exactly."})
    return raw, portions


def build(obj):
    company = lock_company()
    enabled()
    party(obj.party_id, on=obj.date)
    fx, fx_source = rate_for(obj.currency, obj.date, company.base_currency)
    raw, liabilities, vendors = [], [], []
    recognition = convert(obj.amount, fx, company.base_currency)
    bank = None
    dims = {"founder": obj.party_id, "founder_transaction": obj.pk}
    if obj.kind in {"receipt", "reimbursement", "loan_repayment"}:
        bank = (
            BankAccount.objects.select_for_update()
            .filter(pk=obj.bank_id, is_active=True, currency=obj.currency)
            .first()
        )
        if not bank:
            raise ValidationError(
                {"bank_id": "Select an active company bank/cash account in this currency."}
            )
    if obj.kind == "receipt":
        if obj.classification == "payable":
            raise ValidationError(
                {
                    "classification": "Cash funding is a loan, equity or pending classification, "
                    "not an expense reimbursement."
                }
            )
        raw.append(
            {
                "account_id": bank.gl_account_id,
                "currency": obj.currency,
                "debit": str(obj.amount),
                "exchange_rate": str(fx),
                "rate_source": fx_source,
                "dimensions": dims,
            }
        )
    elif obj.kind == "expense":
        source = Expense.objects.select_for_update().get(pk=obj.expense_id)
        if (
            source.status != "draft"
            or source.payment_mode != "founder"
            or source.total != obj.amount
            or source.currency != obj.currency
        ):
            raise BusinessRuleViolation(
                "The founder expense no longer matches its recorded funding."
            )
        recognition, raw = _debits(
            [(source.account_id, source.tax_revision, source.taxable, source.tax)],
            obj.currency,
            fx,
            company.base_currency,
        )
    elif obj.kind == "vendor_payment":
        raw, vendors = _vendor_rows(obj, company)
    elif obj.kind in PAYOUTS:
        raw, liabilities = _liability_rows(obj, company)
    if obj.kind in {"reimbursement", "loan_repayment"}:
        raw.append(
            {
                "account_id": bank.gl_account_id,
                "currency": obj.currency,
                "credit": str(obj.amount),
                "exchange_rate": str(fx),
                "rate_source": fx_source,
                "dimensions": dims,
            }
        )
    else:
        if obj.classification == "loan" and (
            not obj.loan_id
            or obj.loan.party_id != (obj.recipient_id if obj.kind == "reassign" else obj.party_id)
            or obj.loan.currency != obj.currency
            or not obj.loan.is_active
        ):
            raise ValidationError(
                {"loan_id": "Select this founder's active loan agreement in the same currency."}
            )
        if obj.kind == "reassign":
            require(obj.created_by, "founder.liabilities.manage")
            recipient = party(obj.recipient_id, on=obj.date, founder=True)
            if recipient.pk == obj.party_id or obj.classification not in {"payable", "loan"}:
                raise ValidationError(
                    {"recipient_id": "Assign the liability to a different founder."}
                )
            dims = {**dims, "founder": recipient.pk}
        if obj.kind in {"reassign", "reclassify"}:
            recognition = sum((p[2] for p in liabilities), ZERO)
            with localcontext() as context:
                context.prec = 60
                fx = (recognition / obj.amount).quantize(
                    Decimal("0.000000000001"), rounding=ROUND_HALF_UP
                )
            fx_source = "Original liability reclassification"
        if obj.kind == "reclassify" and any(
            o.category == obj.classification for o, _, _ in liabilities
        ):
            raise ValidationError(
                {"classification": "Select a different destination classification."}
            )
        if obj.classification == "share_capital":
            raw.extend(_capital_lines(obj, recognition, fx, fx_source, dims))
        else:
            raw.append(
                {
                    "account_id": control(CONTROLS[obj.classification]).pk,
                    "currency": obj.currency,
                    "credit": str(obj.amount),
                    "base_credit": str(recognition),
                    "exchange_rate": str(fx),
                    "rate_source": fx_source,
                    "valuation": "historical" if obj.kind in {"reclassify", "reassign"} else "spot",
                    "dimensions": dims,
                }
            )
    raw, built, difference, _ = posting.balance_with_fx(raw, company, obj.date)
    quote = strings(
        {
            "lines": [posting.line_payload(line) for line in built],
            "fx_difference": difference,
            "base_currency": company.base_currency,
        }
    )
    # Canonical decimal values survive NUMERIC scale changes on database reads.
    canonical = [
        {
            k: str(Decimal(v).normalize())
            if k in {"debit", "credit", "base_debit", "base_credit", "exchange_rate"}
            else v
            for k, v in line.items()
        }
        for line in quote["lines"]
    ]
    quote["quote_fingerprint"] = posting.fingerprint(
        {"lines": canonical, "base": company.base_currency}
    )
    return {
        "raw": raw,
        "quote": quote,
        "liabilities": liabilities,
        "vendors": vendors,
        "recognition": recognition,
        "rate": fx,
        "company": company,
    }


def _capital_lines(obj, recognition, fx, source, dims):
    enabled("ownership")
    issuance = obj.issuance
    if (
        not issuance
        or issuance.status != "confirmed"
        or issuance.kind not in {"issuance", "opening"}
        or issuance.effective_date > obj.date
        or issuance.share_class.currency != obj.currency
    ):
        raise BusinessRuleViolation(
            "Share capital needs a documented confirmed issuance in this currency, "
            "effective by the funding date."
        )
    rows = issuance.lines.filter(recipient=obj.party)
    capacity = sum((line.price * line.units for line in rows), ZERO)
    prior = total(
        Tx.objects.filter(
            issuance=issuance, party=obj.party, classification="share_capital", status="posted"
        ).exclude(pk=obj.pk)
    )
    if obj.amount + prior > capacity:
        raise BusinessRuleViolation("Funding exceeds this shareholder's documented subscription.")
    nominal_total = sum(
        ((issuance.share_class.par_value or ZERO) * line.units for line in rows), ZERO
    )
    if nominal_total > capacity:
        raise BusinessRuleViolation("Issue price cannot be below the configured par value.")
    nominal = min(obj.amount, max(ZERO, nominal_total - prior))
    premium = obj.amount - nominal
    base_nominal = (
        recognition
        if not premium
        else convert(nominal, fx, lock_company().base_currency)
        if nominal
        else ZERO
    )
    values = [
        ("share_capital", nominal, base_nominal),
        ("share_premium", premium, recognition - base_nominal),
    ]
    return [
        {
            "account_id": control(purpose).pk,
            "currency": obj.currency,
            "credit": str(value),
            "base_credit": str(base),
            "exchange_rate": str(fx),
            "rate_source": source,
            "dimensions": dims,
            "valuation": "allocated",
        }
        for purpose, value, base in values
        if value
    ]


@transaction.atomic
def preview(request, pk):
    require(request.user, "founder.view")
    lock_company()
    obj = Tx.objects.select_for_update().get(pk=pk)
    if obj.status == "posted":
        return obj.snapshot["quote"]
    return build(obj)["quote"]


def _check_quote(plan, data, *, frozen=False):
    supplied = data.get("quote_fingerprint")
    if supplied and supplied != plan["quote"]["quote_fingerprint"]:
        raise BusinessRuleViolation(
            "The financial quote changed. Preview and review again.", code="stale_quote"
        )
    if (frozen or Decimal(plan["quote"]["fx_difference"]) != ZERO) and not supplied:
        raise BusinessRuleViolation(
            "A current financial preview is required.", code="quote_required"
        )
    if Decimal(plan["quote"]["fx_difference"]) != ZERO and not data.get("confirm_fx"):
        raise ValidationError({"confirm_fx": "Confirm the disclosed FX difference."})


@transaction.atomic
def verify(request, pk, quote):
    enabled()
    require(request.user, "founder.verify")
    lock_company()
    obj = Tx.objects.select_for_update().get(pk=pk)
    if obj.status == "posted":
        return obj
    if obj.status != "recorded":
        raise BusinessRuleViolation("Only recorded transactions can be verified.")
    if obj.created_by_id == request.user.pk:
        raise PermissionDenied("The recorder cannot verify their own corporate transaction.")
    require(obj.created_by, "founder.transactions.manage")
    if obj.created_by.must_change_password:
        raise PermissionDenied("The recorder must complete account security requirements first.")
    plan = build(obj)
    _check_quote(plan, quote)
    policy = approvals.policy_for_action("founder.post")
    if (
        policy
        and policy.in_force
        and (policy.amount_threshold is None or plan["recognition"] >= policy.amount_threshold)
    ):
        obj.approval = approvals.submit(
            request,
            action="founder.post",
            title=f"Founder {obj.kind} #{obj.pk}",
            payload={
                "transaction_id": obj.pk,
                "fingerprint": obj.fingerprint,
                "quote": {**quote, "quote_fingerprint": plan["quote"]["quote_fingerprint"]},
            },
            subject_key=str(obj.pk),
        )
        obj.status, obj.verified_by = "awaiting_approval", request.user
        obj.save(update_fields=["approval", "status", "verified_by"])
    else:
        _post(request, obj, request.user, plan)
    return obj


def execute_post(request, approval, approver):
    enabled()
    obj = Tx.objects.select_for_update().get(pk=approval.payload["transaction_id"])
    require(obj.created_by, "founder.transactions.manage")
    require(obj.verified_by, "founder.verify")
    if (
        obj.created_by_id == approver.pk
        or obj.created_by.must_change_password
        or obj.verified_by.must_change_password
        or obj.approval_id != approval.pk
        or obj.status != "awaiting_approval"
        or obj.fingerprint != approval.payload["fingerprint"]
    ):
        raise BusinessRuleViolation(
            "The transaction is no longer eligible for independent approval."
        )
    plan = build(obj)
    _check_quote(plan, approval.payload["quote"], frozen=True)
    _post(request, obj, approver, plan)
    return f"founder:{obj.pk}"


def declined(request, approval):
    obj = Tx.objects.select_for_update().get(pk=approval.payload["transaction_id"])
    if obj.status != "awaiting_approval" or obj.approval_id != approval.pk:
        raise BusinessRuleViolation("The approval no longer belongs to this pending transaction.")
    obj.status = "rejected"
    obj.save(update_fields=["status"])
    record(
        "founder.transaction_rejected",
        request=request,
        target=obj,
        reason=approval.decision_reason or "Approval withdrawn",
    )


@transaction.atomic
def reject(request, pk, reason):
    enabled()
    require(request.user, "founder.transactions.manage")
    lock_company()
    obj = Tx.objects.select_for_update().get(pk=pk)
    if obj.status != "recorded" or not reason.strip():
        raise BusinessRuleViolation("Reject a recorded transaction with a reason.")
    if obj.created_by_id != request.user.pk:
        require(request.user, "founder.verify")
    obj.status = "rejected"
    obj.save(update_fields=["status"])
    record("founder.transaction_rejected", request=request, target=obj, reason=reason)
    return obj


def _post(request, obj, actor, plan):
    require(obj.created_by, "founder.transactions.manage")
    if obj.kind == "expense":
        require(obj.created_by, "expenses.manage")
    if obj.kind in PAYOUTS:
        require(obj.created_by, "founder.liabilities.manage")
    authority = authorize(actor, "founder_transaction", "post")
    journal = posting.post_journal(
        actor=actor,
        authority=authority,
        request_context=request,
        posting_key=f"founder:{obj.pk}:post",
        source_type="founder_transaction",
        source_id=obj.pk,
        source_action="post",
        posting_date=obj.date,
        description=f"Founder {obj.kind} #{obj.pk}",
        lines=plan["raw"],
    )
    obj.journal, obj.base_amount, obj.status, obj.verified_by = (
        journal,
        plan["recognition"],
        "posted",
        actor,
    )
    obj.snapshot = strings(
        {
            "quote": plan["quote"],
            "party_name": str(obj.party),
            "classification": obj.classification,
            "source": obj.request_data,
        }
    )
    obj.save()
    if obj.classification in {"payable", "loan", "pending"} and obj.kind not in {
        "reimbursement",
        "loan_repayment",
    }:
        FounderObligation.objects.create(
            origin=obj,
            recovery_origin=(
                plan["liabilities"][0][0].recovery_origin or plan["liabilities"][0][0].origin
            )
            if plan["liabilities"]
            else obj,
            party_id=obj.recipient_id if obj.kind == "reassign" else obj.party_id,
            category=obj.classification,
            currency=obj.currency,
            amount=obj.amount,
            base_amount=plan["recognition"],
            original_expense=obj.expense
            or next(
                (o.original_expense for o, _, _ in plan["liabilities"] if o.original_expense_id),
                None,
            ),
        )
    for obligation, value, base in plan["liabilities"]:
        ObligationAllocation.objects.create(
            transaction=obj, obligation=obligation, amount=value, base_amount=base
        )
    for kind, source, value, base in plan["vendors"]:
        FounderVendorAllocation.objects.create(
            transaction=obj, amount=value, base_amount=base, **{kind: source}
        )
        source.amount_paid += value
        source.base_settled += base
        source.status = "paid" if source.amount_paid == source.total else "partially_paid"
        source.save(update_fields=["amount_paid", "base_settled", "status"])
    if obj.kind == "expense":
        source = obj.expense
        source.number = next_number(
            "expense", obj.date, lambda n: Expense.objects.filter(number=n).exists()
        )
        source.journal, source.base_total, source.exchange_rate = (
            journal,
            plan["recognition"],
            plan["rate"],
        )
        source.status, source.posted_by, source.posted_at = "paid", actor, timezone.now()
        source.save()
    record(
        "founder.transaction_posted",
        request=request,
        target=obj,
        after={"journal": journal.number, "kind": obj.kind, "amount": obj.amount},
    )


def overlap_allocations(obligation):
    root = obligation.recovery_origin or obligation.origin
    return PersonalAllocation.objects.filter(
        settlement__status="confirmed",
        settlement__is_return=False,
        settlement__recipient_id=obligation.party_id,
    ).filter(
        Q(obligation__sharing__expense_id=root.expense_id)
        if root.expense_id
        else Q(obligation__sharing__founder_payment_id=root.pk)
    )


def assert_recovery_safe(obligation, proposed):
    """Block overlapping recovery. Personal records never change GL liabilities."""
    root = obligation.recovery_origin or obligation.origin
    personal = ZERO
    for allocation in overlap_allocations(obligation).select_related("settlement"):
        refunds = total(
            PersonalAllocation.objects.filter(
                settlement__returns=allocation.settlement,
                settlement__status="confirmed",
                obligation=allocation.obligation,
            )
        )
        ratio_return = min(allocation.amount, refunds)
        resolved = total(
            RecoveryResolution.objects.filter(
                obligation__recovery_origin=root,
                obligation__party=obligation.party,
                settlement=allocation.settlement,
            )
        )
        personal += max(ZERO, allocation.amount - ratio_return - resolved)
    already = total(
        ObligationAllocation.objects.filter(
            obligation__recovery_origin=root,
            transaction__party=obligation.party,
            transaction__status="posted",
            transaction__kind__in=["reimbursement", "loan_repayment"],
        )
    )
    if personal + already + proposed > root.amount:
        raise BusinessRuleViolation(
            "Reimbursement would duplicate personal recovery. Record an authorized, "
            "audited return or corporate liability resolution first.",
            code="duplicate_recovery_blocked",
        )


@transaction.atomic
def resolve_recovery(request, data):
    enabled()
    require(request.user, "founder.liabilities.manage", "founder.verify")
    lock_company()
    obligation = get_object_or_404(
        FounderObligation.objects.select_for_update(), pk=data["obligation_id"]
    )
    settlement_id = data["settlement_id"]
    overlaps = overlap_allocations(obligation).filter(settlement_id=settlement_id)
    returned = sum(
        (
            min(
                allocation.amount,
                total(
                    PersonalAllocation.objects.filter(
                        obligation=allocation.obligation,
                        settlement__returns=allocation.settlement,
                        settlement__status="confirmed",
                    )
                ),
            )
            for allocation in overlaps
        ),
        ZERO,
    )
    available = (
        total(overlaps)
        - returned
        - total(
            RecoveryResolution.objects.filter(
                obligation__recovery_origin=obligation.recovery_origin or obligation.origin,
                obligation__party=obligation.party,
                settlement_id=settlement_id,
            )
        )
    )
    value = positive(data["amount"], obligation.currency)
    if value > available or not data["reason"].strip():
        raise BusinessRuleViolation(
            "The resolution must identify an unresolved overlap and a reason."
        )
    corporate = Tx.objects.filter(
        pk=data.get("corporate_transaction_id"),
        status="posted",
        kind="reassign",
        party=obligation.party,
    ).first()
    if (
        not corporate
        or corporate.recipient_id != overlaps.first().settlement.payer_id
        or total(corporate.allocations.filter(obligation=obligation)) < value
    ):
        raise BusinessRuleViolation(
            "A posted, independently verified liability reassignment to the personal payer "
            "is required. Confirmed personal returns are accounted for directly."
        )
    if (
        total(RecoveryResolution.objects.filter(corporate_transaction=corporate)) + value
        > corporate.amount
    ):
        raise BusinessRuleViolation(
            "This corporate reassignment is already allocated to another resolution."
        )
    obj = RecoveryResolution.objects.create(
        obligation=obligation,
        settlement_id=settlement_id,
        corporate_transaction=corporate,
        amount=value,
        reason=data["reason"],
        authorized_by=request.user,
    )
    record(
        "founder.recovery_resolved",
        request=request,
        target=obj,
        after={"corporate_transaction": corporate.pk, "amount": value},
        reason=obj.reason,
    )
    return obj


@transaction.atomic
def reverse(request, pk, on, reason):
    enabled()
    require(request.user, "founder.verify", "founder.liabilities.manage")
    lock_company()
    obj = Tx.objects.select_for_update().get(pk=pk)
    if obj.status != "posted" or not reason.strip():
        raise BusinessRuleViolation("Only posted transactions can be reversed with a reason.")
    if (
        obj.designations.exists()
        or hasattr(obj, "personal_sharing")
        or obj.recovery_resolutions.exists()
    ):
        raise BusinessRuleViolation(
            "Resolve dependent funding, personal sharing or recovery records before reversal."
        )
    obligation = FounderObligation.objects.filter(origin=obj).first()
    if obligation and obligation.allocations.filter(transaction__status="posted").exists():
        raise BusinessRuleViolation("Reverse the dependent corporate settlements first.")
    obj.reversal_journal = posting.reverse(
        request,
        obj.journal_id,
        on_date(on),
        reason,
        f"founder:{obj.pk}:reverse",
        authority=authorize(request.user, "founder_transaction", "reverse"),
    )
    for allocation in obj.vendor_allocations.select_related("bill", "expense"):
        source = allocation.bill or allocation.expense
        source.amount_paid -= allocation.amount
        source.base_settled -= allocation.base_amount
        source.status = "partially_paid" if source.amount_paid else "posted"
        source.save(update_fields=["amount_paid", "base_settled", "status"])
    if obj.expense_id:
        obj.expense.status, obj.expense.void_journal, obj.expense.void_reason = (
            "void",
            obj.reversal_journal,
            reason,
        )
        obj.expense.save(update_fields=["status", "void_journal", "void_reason"])
    obj.status = "reversed"
    obj.save(update_fields=["status", "reversal_journal"])
    record("founder.transaction_reversed", request=request, target=obj, reason=reason)
    return obj
