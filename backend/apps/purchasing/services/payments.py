"""Vendor payments: Dr payable (historical base) / Cr bank (Phase 3 carrying value) / FX.

A payment must be fully allocated to posted bills or accrued expenses of one vendor in
the bank account's currency; vendor advances are not supported in Phase 4. Like
treasury, the preview returns a quote fingerprint; a confirmation with a stale quote
(rates or bank book value changed) is refused and must be previewed again.
"""

from decimal import Context, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounting.money import ZERO, convert, money, strings
from apps.accounting.services import posting
from apps.accounting.services.adapters import authorize
from apps.accounting.services.setup import lock_company, rate_for
from apps.accounts.authorization import require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.banking.models import BankAccount
from apps.billing.services import common
from apps.company.services import next_number
from apps.core.exceptions import BusinessRuleViolation

from ..models import Expense, Vendor, VendorBill, VendorPayment, VendorPaymentAllocation

OPEN = ("posted", "partially_paid")


def _targets(vendor, currency, rows, *, lock):
    """Resolve allocations to (document, amount); every document is locked in pk order."""
    bills = [r["bill_id"] for r in rows if r.get("bill_id")]
    expenses = [r["expense_id"] for r in rows if r.get("expense_id")]
    bill_qs = VendorBill.objects.filter(pk__in=bills).order_by("pk")
    expense_qs = Expense.objects.filter(pk__in=expenses, payment_mode="accrued").order_by("pk")
    if lock:
        bill_qs, expense_qs = bill_qs.select_for_update(), expense_qs.select_for_update()
    found = {("bill", d.pk): d for d in bill_qs} | {("expense", d.pk): d for d in expense_qs}
    out = []
    for row in rows:
        key = (
            ("bill", row.get("bill_id"))
            if row.get("bill_id")
            else ("expense", row.get("expense_id"))
        )
        doc = found.get(key)
        if doc is None:
            raise ValidationError({"allocations": "Allocate to posted bills or accrued expenses."})
        amount = common.positive(money(row.get("amount"), currency, "allocations.amount"))
        if doc.vendor_id != vendor.pk:
            raise ValidationError({"allocations": f"{doc} belongs to another vendor."})
        if doc.currency != currency:
            raise ValidationError(
                {
                    "allocations": (
                        f"{doc} is in {doc.currency}; pay it from a {doc.currency} account."
                    )
                }
            )
        if doc.status not in OPEN:
            raise ValidationError({"allocations": f"{doc} is not open for payment."})
        if amount > doc.total - doc.amount_paid:
            raise BusinessRuleViolation(
                f"{doc} has only {doc.total - doc.amount_paid} outstanding.", code="overallocation"
            )
        out.append((key[0], doc, amount))
    if len({(k, d.pk) for k, d, _ in out}) != len(out):
        raise ValidationError({"allocations": "Allocate to each document once."})
    return out


def _build(data, *, lock):
    company = lock_company()
    base = company.base_currency
    vendor = Vendor.objects.filter(pk=data.get("vendor_id")).first()
    bank_qs = BankAccount.objects.filter(pk=data.get("bank_account_id"), is_active=True)
    bank = (bank_qs.select_for_update() if lock else bank_qs).first()
    if vendor is None or bank is None:
        raise ValidationError(
            {"bank_account_id": "Choose the vendor and an active paying account."}
        )
    on = data.get("payment_date") or timezone.localdate()
    amount = common.positive(money(data.get("amount"), bank.currency))
    targets = _targets(vendor, bank.currency, data.get("allocations") or [], lock=lock)
    if sum((a for _, _, a in targets), ZERO) != amount:
        raise ValidationError(
            {"allocations": "Allocate the full payment; vendor advances are not supported yet."}
        )
    payable = common.control("payable")
    rate, source = rate_for(bank.currency, on, base)
    raw, portions = [], []
    for kind, doc, value in targets:
        portion = common.settlement_base(
            value,
            total=doc.total,
            base_total=doc.base_total,
            native_settled=doc.amount_paid,
            base_settled=doc.base_settled,
            rate=doc.exchange_rate,
            base=base,
        )
        portions.append((kind, doc, value, portion))
        raw.append(
            {
                "account_id": payable.pk,
                "currency": bank.currency,
                "debit": str(value),
                "base_debit": str(portion),
                "exchange_rate": str(doc.exchange_rate),
                "rate_source": f"Historical rate of {doc.number}",
                "valuation": "historical",
                "description": f"Settles {doc.number}",
                "dimensions": {"vendor": vendor.pk, kind: doc.pk},
            }
        )
    raw.append(
        {
            "account_id": bank.gl_account_id,
            "currency": bank.currency,
            "credit": str(amount),
            "exchange_rate": str(rate),
            "rate_source": source,
            "description": f"Payment to {vendor.name}",
        }
    )
    raw, built, difference, fx = posting.balance_with_fx(raw, company, on)
    quote = strings(
        {
            "lines": [posting.line_payload(line) for line in built],
            "fx_difference": difference,
            "fx_account": str(fx) if fx else None,
            "base_currency": base,
        }
    )
    # Decimal scale changes on a database round trip must not invalidate a quote.
    identity = {**quote, "lines": [dict(line) for line in quote["lines"]]}
    for line in identity["lines"]:
        for key in ("debit", "credit", "base_debit", "base_credit", "exchange_rate"):
            line[key] = format(Decimal(line[key]).normalize(context=Context(prec=60)), "f")
    identity["fx_difference"] = format(
        Decimal(identity["fx_difference"]).normalize(context=Context(prec=60)), "f"
    )
    quote["quote_fingerprint"] = posting.fingerprint(identity)
    return {
        "vendor": vendor,
        "bank": bank,
        "on": on,
        "amount": amount,
        "rate": rate,
        "raw": raw,
        "built": built,
        "portions": portions,
        "difference": difference,
        "quote": quote,
    }


@transaction.atomic
def preview(request, data):
    require(request.user, "vendor_payments.manage")
    return _build(data, lock=False)["quote"]


def _key(key):
    if not isinstance(key, str) or not 8 <= len(key) <= 160:
        raise ValidationError({"posting_key": "Send a stable Idempotency-Key of 8–160 characters."})
    return key


def _check_quote(plan, data, *, required=False):
    expected = data.get("quote_fingerprint")
    if (required and not expected) or (expected and expected != plan["quote"]["quote_fingerprint"]):
        raise BusinessRuleViolation(
            "Rates or book values changed. Preview the payment again; reject and resubmit "
            "an existing approval request with a fresh quote.",
            code="stale_quote",
        )
    if plan["difference"]:
        if not expected:
            raise ValidationError(
                {"quote_fingerprint": "Preview the payment before confirming FX."}
            )
        if not data.get("confirm_fx"):
            raise ValidationError(
                {"confirm_fx": "Review the disclosed FX difference and confirm before paying."}
            )


@transaction.atomic
def pay(request, data, key):
    require(request.user, "vendor_payments.manage")
    company = lock_company()
    key = _key(key)
    digest = posting.fingerprint(
        {k: v for k, v in data.items() if k not in ("quote_fingerprint", "confirm_fx")}
    )
    existing = VendorPayment.objects.filter(client_key=key).first()
    if existing:
        if existing.fingerprint != digest:
            raise BusinessRuleViolation(
                "The idempotency key was used for a different payment.", code="idempotency_conflict"
            )
        return existing
    plan = _build(data, lock=True)
    _check_quote(plan, data)
    confirmed_data = {**data, "quote_fingerprint": plan["quote"]["quote_fingerprint"]}
    payment = VendorPayment.objects.create(
        number=next_number(
            "vendor_payment", plan["on"], lambda n: VendorPayment.objects.filter(number=n).exists()
        ),
        client_key=key,
        fingerprint=digest,
        vendor=plan["vendor"],
        bank_account=plan["bank"],
        payment_date=plan["on"],
        currency=plan["bank"].currency,
        amount=plan["amount"],
        method=data.get("method", "bank_transfer"),
        reference=(data.get("reference") or "")[:120],
        notes=(data.get("notes") or "")[:1000],
        status=VendorPayment.Status.AWAITING_APPROVAL,
        created_by=request.user,
    )
    for kind, doc, value, _ in plan["portions"]:
        VendorPaymentAllocation.objects.create(payment=payment, amount=value, **{kind: doc})
    policy = approvals.policy_for_action("vendor_payment.post")
    base_amount = convert(plan["amount"], plan["rate"], company.base_currency)
    if (
        policy
        and policy.in_force
        and (policy.amount_threshold is None or base_amount >= policy.amount_threshold)
    ):
        payment.approval = approvals.submit(
            request,
            action="vendor_payment.post",
            subject_key=f"vendor_payment:{payment.pk}",
            title=f"Pay {payment.vendor.name} — {payment.currency} {payment.amount}"[:200],
            payload=strings(
                {
                    "payment_id": payment.pk,
                    "data": confirmed_data,
                }
            ),
        )
        payment.save(update_fields=["approval"])
        record("purchasing.vendor_payment_requested", request=request, target=payment)
        return payment
    return _post(request, payment, request.user, confirmed_data)


def execute_payment(request, approval, approver):
    payment = VendorPayment.objects.select_for_update().get(pk=approval.payload["payment_id"])
    if payment.status != VendorPayment.Status.AWAITING_APPROVAL:
        raise BusinessRuleViolation("The payment is no longer awaiting approval.")
    # Re-derive and compare with the requester's frozen quote, never silently reconfirm FX.
    _post(request, payment, approver, approval.payload["data"])
    return f"vendor_payment:{payment.pk}"


def sync_payment(payment):
    if (
        payment.status == VendorPayment.Status.AWAITING_APPROVAL
        and payment.approval_id
        and payment.approval.status in ("rejected", "cancelled")
    ):
        payment.status = VendorPayment.Status.REJECTED
        payment.save(update_fields=["status"])
    return payment


def _post(request, payment, actor, data):
    authority = authorize(actor, "vendor_payment", "pay")
    plan = _build(
        {
            **data,
            "vendor_id": payment.vendor_id,
            "bank_account_id": payment.bank_account_id,
            "payment_date": payment.payment_date,
            "amount": str(payment.amount),
        },
        lock=True,
    )
    _check_quote(plan, data, required=True)
    journal = posting.post_journal(
        actor=actor,
        authority=authority,
        request_context=request,
        posting_key=common.posting_key("vendor_payment", payment.pk, "pay"),
        source_type="vendor_payment",
        source_id=payment.pk,
        source_action="pay",
        posting_date=payment.payment_date,
        description=f"Vendor payment {payment.number} — {payment.vendor.name}"[:500],
        lines=plan["raw"],
    )
    allocations = {(a.bill_id, a.expense_id): a for a in payment.allocations.all()}
    for kind, doc, value, portion in plan["portions"]:
        doc.amount_paid += value
        doc.base_settled += portion
        doc.status = "paid" if doc.amount_paid == doc.total else "partially_paid"
        doc.save(update_fields=["amount_paid", "base_settled", "status"])
        allocation = allocations[(doc.pk, None) if kind == "bill" else (None, doc.pk)]
        allocation.base_amount = portion
        allocation.save(update_fields=["base_amount"])
    payment.journal = journal
    bank_account_id = payment.bank_account.gl_account_id
    payment.base_amount = next(
        line.base_credit for line in plan["built"] if line.account_id == bank_account_id
    )
    payment.status = VendorPayment.Status.PAID
    payment.save()
    record(
        "purchasing.vendor_paid", request=request, target=payment, after={"journal": journal.number}
    )
    return payment


@transaction.atomic
def reverse(request, pk, reason, on=None):
    authority = authorize(request.user, "vendor_payment", "reverse")
    lock_company()
    payment = VendorPayment.objects.select_for_update().filter(pk=pk).first()
    if payment is None:
        raise NotFound()
    if not reason.strip():
        raise ValidationError({"reason": "Explain the reversal."})
    if payment.status == VendorPayment.Status.REVERSED:
        return payment
    if payment.status != VendorPayment.Status.PAID:
        raise BusinessRuleViolation("Only posted vendor payments can be reversed.")
    payment.reversal_journal = posting.reverse(
        request,
        payment.journal_id,
        on or timezone.localdate(),
        reason.strip()[:500],
        common.posting_key("vendor_payment", payment.pk, "reverse"),
        authority=authority,
    )
    for allocation in payment.allocations.select_related("bill", "expense"):
        doc = allocation.bill or allocation.expense
        doc = type(doc).objects.select_for_update().get(pk=doc.pk)
        doc.amount_paid -= allocation.amount
        doc.base_settled -= allocation.base_amount
        doc.status = "partially_paid" if doc.amount_paid else "posted"
        doc.save(update_fields=["amount_paid", "base_settled", "status"])
    payment.status = VendorPayment.Status.REVERSED
    payment.save()
    record("purchasing.vendor_payment_reversed", request=request, target=payment, reason=reason)
    return payment
