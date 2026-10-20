"""Credit notes (corrections), customer credit, credit application and refunds (money out).

A credit note never edits the original invoice. It reverses revenue and output tax at
the invoice's historical rate, reduces the receivable up to the amount still open, and
holds any excess (for already-paid invoices) as customer credit. A refund is a separate
outflow from a bank account that consumes customer credit.
"""

from decimal import ROUND_HALF_UP, localcontext

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounting.money import ZERO, convert, money, quantum, strings
from apps.accounting.services import posting
from apps.accounting.services.adapters import authorize
from apps.accounting.services.setup import lock_company, rate_for
from apps.accounts.authorization import require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.banking.models import BankAccount
from apps.company.services import next_number
from apps.core.exceptions import BusinessRuleViolation
from apps.sales import calculation
from apps.sales.models import Customer

from ..models import (
    CreditApplication,
    CreditNote,
    CreditNoteLine,
    CustomerCreditMovement,
    Invoice,
    Refund,
)
from . import common
from .invoices import reserved, settle_status


def credit_balance(customer_id, currency, *, lock=False):
    """(native, base) customer credit available in ``currency``."""
    if lock:
        # Serialize credit use per customer on the customer row.
        Customer.objects.select_for_update().filter(pk=customer_id).first()
    agg = CustomerCreditMovement.objects.filter(
        customer_id=customer_id, currency=currency
    ).aggregate(n=Sum("amount"), b=Sum("base_amount"))
    return agg["n"] or ZERO, agg["b"] or ZERO


def _carrying(amount, native, base, currency):
    """Base value of ``amount`` of credit: weighted average, exact on full use."""
    if amount > native:
        raise BusinessRuleViolation("The customer does not have enough credit in this currency.")
    if amount == native:
        return base
    with localcontext() as ctx:
        ctx.prec = 60
        return (amount * base / native).quantize(quantum(currency), rounding=ROUND_HALF_UP)


def _policy_applies(action, base_amount):
    policy = approvals.policy_for_action(action)
    return bool(
        policy
        and policy.in_force
        and (policy.amount_threshold is None or base_amount >= policy.amount_threshold)
    )


def _key(key):
    if not isinstance(key, str) or not 8 <= len(key) <= 160:
        raise ValidationError({"posting_key": "Send a stable Idempotency-Key of 8–160 characters."})
    return key


# ---------------------------------------------------------------- credit notes


def _credit_lines(invoice, data):
    """Per invoice line: (line, taxable, tax). ``full`` credits everything still creditable."""
    lines = {
        line.pk: line for line in invoice.lines.select_related("tax_revision", "revenue_account")
    }
    if data.get("full"):
        requested = [
            (line, line.taxable - line.credited_taxable + line.tax - line.credited_tax)
            for line in lines.values()
        ]
    else:
        requested = []
        for row in data.get("lines") or []:
            line = lines.get(row.get("invoice_line_id"))
            if line is None:
                raise ValidationError({"lines": "Credit lines must belong to the invoice."})
            requested.append(
                (line, common.positive(money(row.get("amount"), invoice.currency, "lines.amount")))
            )
    out = []
    for line, gross in requested:
        open_taxable = line.taxable - line.credited_taxable
        open_tax = line.tax - line.credited_tax
        if gross <= 0:
            continue
        if gross > open_taxable + open_tax:
            raise BusinessRuleViolation(
                f"Line {line.position} has only {open_taxable + open_tax} left to credit.",
                code="overcredit",
            )
        if gross == open_taxable + open_tax:
            tax = open_tax
        else:
            with localcontext() as ctx:
                ctx.prec = 60
                tax = (gross * line.tax / line.total).quantize(
                    quantum(invoice.currency), rounding=ROUND_HALF_UP
                )
            tax = min(tax, open_tax)
        out.append((line, gross - tax, tax))
    if not out:
        raise ValidationError({"lines": "Nothing left to credit on this invoice."})
    return out


@transaction.atomic
def request_credit_note(request, invoice_pk, data, key):
    require(request.user, "credit_notes.manage")
    company = lock_company()
    key = _key(key)
    digest = posting.fingerprint({"invoice_id": str(invoice_pk), "data": data})
    existing = CreditNote.objects.filter(client_key=key).first()
    if existing:
        if not existing.fingerprint or existing.fingerprint != digest:
            raise BusinessRuleViolation(
                "The idempotency key was used for another credit note.", code="idempotency_conflict"
            )
        return existing
    invoice = Invoice.objects.select_for_update().filter(pk=invoice_pk).first()
    if invoice is None:
        raise NotFound()
    if invoice.status not in Invoice.ISSUED_STATES:
        raise BusinessRuleViolation("Only issued invoices can be credited.")
    if CreditNote.objects.filter(
        invoice=invoice, status=CreditNote.Status.AWAITING_APPROVAL
    ).exists():
        raise BusinessRuleViolation("Another credit note for this invoice is awaiting approval.")
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise ValidationError({"reason": "Explain the credit."})
    parts = _credit_lines(invoice, data)
    total = sum((t + x for _, t, x in parts), ZERO)
    on = data.get("issue_date") or timezone.localdate()
    if on < invoice.issue_date:
        raise ValidationError({"issue_date": "A credit note cannot precede its invoice."})
    note = CreditNote.objects.create(
        client_key=key,
        fingerprint=digest,
        invoice=invoice,
        customer=invoice.customer,
        issue_date=on,
        reason=reason[:500],
        currency=invoice.currency,
        taxable=sum((t for _, t, _ in parts), ZERO),
        tax=sum((x for _, _, x in parts), ZERO),
        total=total,
        applied_amount=total,
        status=CreditNote.Status.AWAITING_APPROVAL,
        created_by=request.user,
    )
    for line, taxable, tax in parts:
        CreditNoteLine.objects.create(credit_note=note, invoice_line=line, taxable=taxable, tax=tax)
    if _policy_applies(
        "credit_note.issue", convert(total, invoice.exchange_rate, company.base_currency)
    ):
        note.approval = approvals.submit(
            request,
            action="credit_note.issue",
            subject_key=f"credit_note:{note.pk}",
            title=f"Credit {invoice.number} — {invoice.currency} {total}"[:200],
            payload=strings({"credit_note_id": note.pk, "total": total}),
            reason=note.reason,
        )
        note.save(update_fields=["approval"])
        record(
            "billing.credit_note_requested", request=request, target=note, after={"total": total}
        )
        return note
    return _issue_credit_note(request, note, request.user)


def execute_credit_note(request, approval, approver):
    note = CreditNote.objects.select_for_update().get(pk=approval.payload["credit_note_id"])
    if note.status != CreditNote.Status.AWAITING_APPROVAL:
        raise BusinessRuleViolation("The credit note is no longer awaiting approval.")
    _issue_credit_note(request, note, approver)
    return f"credit_note:{note.pk}"


def sync_credit_note(note):
    if (
        note.status == CreditNote.Status.AWAITING_APPROVAL
        and note.approval_id
        and note.approval.status in ("rejected", "cancelled")
    ):
        note.status = CreditNote.Status.REJECTED
        note.save(update_fields=["status"])
    return note


def _issue_credit_note(request, note, actor):
    authority = authorize(actor, "credit_note", "issue")
    company = lock_company()
    base = company.base_currency
    branding = common.published_branding()
    invoice = Invoice.objects.select_for_update().get(pk=note.invoice_id)
    if invoice.status not in Invoice.ISSUED_STATES:
        raise BusinessRuleViolation("The invoice can no longer be credited.")
    parts = [
        (cl, cl.invoice_line, cl.taxable, cl.tax)
        for cl in note.lines.select_related("invoice_line__tax_revision", "invoice_line__tax_code")
    ]
    for _, line, taxable, tax in parts:
        line.refresh_from_db()
        if taxable > line.taxable - line.credited_taxable or tax > line.tax - line.credited_tax:
            raise BusinessRuleViolation(
                "The invoice was credited in the meantime.", code="overcredit"
            )
    applied = min(note.total, invoice.outstanding - reserved(invoice))
    applied = max(applied, ZERO)
    excess = note.total - applied
    rate = invoice.exchange_rate
    fx = {"exchange_rate": str(rate), "rate_source": f"Historical rate of {invoice.number}"}
    debits = {}
    for _, line, taxable, tax in parts:
        if taxable:
            key = (line.revenue_account_id, None)
            debits[key] = debits.get(key, ZERO) + taxable
        if tax:
            key = (line.tax_revision.output_account_id, line.tax_revision_id)
            debits[key] = debits.get(key, ZERO) + tax
    base_total = convert(note.total, rate, base)
    keys = list(debits)
    bases = calculation.allocate(base_total, [debits[k] for k in keys], base)
    raw = [
        {
            "account_id": account_id,
            "currency": invoice.currency,
            "debit": str(debits[(account_id, rev)]),
            "base_debit": str(b),
            "tax_revision_id": rev,
            "description": "Output tax reversed" if rev else "Revenue reversed",
            "valuation": "allocated",
            **fx,
        }
        for (account_id, rev), b in zip(keys, bases, strict=True)
    ]
    ar_base = ZERO
    if applied:
        ar_base = common.settlement_base(
            applied,
            total=invoice.total - invoice.amount_paid,
            base_total=invoice.base_total,
            native_settled=invoice.amount_credited,
            base_settled=invoice.base_settled,
            rate=rate,
            base=base,
        )
        raw.append(
            {
                "account_id": common.control("receivable").pk,
                "currency": invoice.currency,
                "credit": str(applied),
                "base_credit": str(ar_base),
                "description": f"Credits {invoice.number}",
                "valuation": "historical",
                "dimensions": {"customer": invoice.customer_id, "invoice": invoice.pk},
                **fx,
            }
        )
    credit_base = ZERO
    if excess:
        credit_base = convert(excess, rate, base)
        raw.append(
            {
                "account_id": common.control("customer_credit").pk,
                "currency": invoice.currency,
                "credit": str(excess),
                "base_credit": str(credit_base),
                "description": "Credit in excess of the open balance held for the customer",
                "dimensions": {"customer": invoice.customer_id},
                **fx,
            }
        )
    raw, _, _, _ = posting.balance_with_fx(raw, company, note.issue_date)
    number = next_number(
        "credit_note", note.issue_date, lambda n: CreditNote.objects.filter(number=n).exists()
    )
    journal = posting.post_journal(
        actor=actor,
        authority=authority,
        request_context=request,
        posting_key=common.posting_key("credit_note", note.pk, "issue"),
        source_type="credit_note",
        source_id=note.pk,
        source_action="issue",
        posting_date=note.issue_date,
        description=f"Credit note {number} for {invoice.number}"[:500],
        lines=raw,
        reason=note.reason,
    )
    for _, line, taxable, tax in parts:
        line.credited_taxable += taxable
        line.credited_tax += tax
        line.save(update_fields=["credited_taxable", "credited_tax"])
    invoice.amount_credited += applied
    invoice.base_settled += ar_base
    settle_status(invoice)
    invoice.save(update_fields=["amount_credited", "base_settled", "status"])
    if excess:
        CustomerCreditMovement.objects.create(
            customer=invoice.customer,
            currency=invoice.currency,
            amount=excess,
            base_amount=credit_base,
            kind="credit_note",
            credit_note=note,
        )
    note.number = number
    note.status = CreditNote.Status.ISSUED
    note.applied_amount, note.credit_amount = applied, excess
    note.base_total = base_total
    note.journal = journal
    note.branding_version = branding
    note.snapshot = _snapshot(note, invoice, parts, number=number, applied=applied, excess=excess)
    note.pdf_status = "pending"
    note.save()
    record(
        "billing.credit_note_issued",
        request=request,
        target=note,
        after={"number": number, "total": note.total, "applied": applied, "credit": excess},
    )
    return note


def _snapshot(note, invoice, parts, *, number, applied, excess):
    """Self-contained credit-note document: credited lines, taxes and totals."""
    source = invoice.snapshot
    inclusive = source.get("prices_include_tax")
    lines, taxes = [], {}
    for _, line, taxable, tax in parts:
        shown = taxable + tax if inclusive else taxable
        lines.append(
            {
                "position": line.position,
                "description": line.description,
                "quantity": "1",
                "unit_price": shown,
                "discount_type": "percent",
                "discount_value": "0",
                "line_discount": "0",
                "amount": shown,
                "tax_rate": line.tax_rate,
            }
        )
        if tax:
            code = line.tax_code.code if line.tax_code else ""
            entry = taxes.setdefault(
                (code, line.tax_rate),
                {"code": code, "rate": line.tax_rate, "taxable": ZERO, "tax": ZERO},
            )
            entry["taxable"] += taxable
            entry["tax"] += tax
    subtotal = sum((x["amount"] for x in lines), ZERO)
    return strings(
        {
            **{
                k: source[k]
                for k in (
                    "customer",
                    "company",
                    "format",
                    "tax_label",
                    "tax_registration_label",
                    "currency",
                    "project",
                    "milestone",
                )
            },
            "number": number,
            "issue_date": note.issue_date,
            "reason": note.reason,
            "invoice_number": invoice.number,
            "invoice_issue_date": invoice.issue_date,
            "prices_include_tax": inclusive,
            "lines": lines,
            "taxes": list(taxes.values()),
            "totals": {
                "subtotal": subtotal,
                "line_discount": ZERO,
                "document_discount": ZERO,
                "taxable": note.taxable,
                "tax": note.tax,
                "total": note.total,
            },
            "applied": applied,
            "credit": excess,
        }
    )


# ---------------------------------------------------------------- credit application


@transaction.atomic
def apply_credit(request, data, key):
    authority = authorize(request.user, "credit_application", "apply")
    company = lock_company()
    key = _key(key)
    digest = posting.fingerprint(data)
    existing = CreditApplication.objects.filter(client_key=key).first()
    if existing:
        if not existing.fingerprint or existing.fingerprint != digest:
            raise BusinessRuleViolation(
                "The idempotency key was used for a different credit application.",
                code="idempotency_conflict",
            )
        return existing
    invoice = Invoice.objects.select_for_update().filter(pk=data.get("invoice_id")).first()
    if invoice is None:
        raise NotFound()
    if invoice.status not in ("issued", "partially_paid"):
        raise BusinessRuleViolation("The invoice is not open.")
    amount = common.positive(money(data.get("amount"), invoice.currency))
    native, base_balance = credit_balance(invoice.customer_id, invoice.currency, lock=True)
    if amount > invoice.outstanding - reserved(invoice):
        raise BusinessRuleViolation(
            "The application exceeds the invoice's open balance.", code="overallocation"
        )
    carrying = _carrying(amount, native, base_balance, invoice.currency)
    base = company.base_currency
    ar_base = common.settlement_base(
        amount,
        total=invoice.total - invoice.amount_credited,
        base_total=invoice.base_total,
        native_settled=invoice.amount_paid,
        base_settled=invoice.base_settled,
        rate=invoice.exchange_rate,
        base=base,
    )
    on = data.get("application_date") or timezone.localdate()
    raw = [
        {
            "account_id": common.control("customer_credit").pk,
            "currency": invoice.currency,
            "debit": str(amount),
            "base_debit": str(carrying),
            "exchange_rate": str(rate_for(invoice.currency, on, base)[0]),
            "rate_source": "Customer credit carrying value",
            "valuation": "historical",
            "description": "Customer credit applied",
            "dimensions": {"customer": invoice.customer_id},
        },
        {
            "account_id": common.control("receivable").pk,
            "currency": invoice.currency,
            "credit": str(amount),
            "base_credit": str(ar_base),
            "exchange_rate": str(invoice.exchange_rate),
            "rate_source": f"Historical rate of {invoice.number}",
            "description": f"Settles {invoice.number}",
            "valuation": "historical",
            "dimensions": {"customer": invoice.customer_id, "invoice": invoice.pk},
        },
    ]
    raw, _, _, _ = posting.balance_with_fx(raw, company, on)
    application = CreditApplication(
        customer=invoice.customer,
        invoice=invoice,
        application_date=on,
        currency=invoice.currency,
        amount=amount,
        base_amount=ar_base,
        client_key=key,
        fingerprint=digest,
        created_by=request.user,
    )
    application.journal = posting.post_journal(
        actor=request.user,
        authority=authority,
        request_context=request,
        posting_key=common.posting_key("credit_application", key),
        source_type="credit_application",
        source_id=key,
        source_action="apply",
        posting_date=on,
        description=f"Customer credit applied to {invoice.number}"[:500],
        lines=raw,
    )
    application.save()
    CustomerCreditMovement.objects.create(
        customer=invoice.customer,
        currency=invoice.currency,
        amount=-amount,
        base_amount=-carrying,
        kind="application",
        application=application,
    )
    invoice.amount_paid += amount
    invoice.base_settled += ar_base
    settle_status(invoice)
    invoice.save(update_fields=["amount_paid", "base_settled", "status"])
    record(
        "billing.credit_applied",
        request=request,
        target=application,
        after={"invoice": invoice.number, "amount": amount},
    )
    return application


# ---------------------------------------------------------------- refunds


@transaction.atomic
def request_refund(request, data, key):
    require(request.user, "credit_notes.manage")
    company = lock_company()
    key = _key(key)
    digest = posting.fingerprint(data)
    existing = Refund.objects.filter(client_key=key).first()
    if existing:
        if not existing.fingerprint or existing.fingerprint != digest:
            raise BusinessRuleViolation(
                "The idempotency key was used for a different refund.",
                code="idempotency_conflict",
            )
        return existing
    customer = Customer.objects.filter(pk=data.get("customer_id")).first()
    bank = BankAccount.objects.filter(pk=data.get("bank_account_id"), is_active=True).first()
    if customer is None or bank is None:
        raise ValidationError(
            {"bank_account_id": "Choose the customer and the paying bank account."}
        )
    amount = common.positive(money(data.get("amount"), bank.currency))
    native, _ = credit_balance(customer.pk, bank.currency, lock=True)
    pending = (
        Refund.objects.filter(
            customer=customer, currency=bank.currency, status=Refund.Status.AWAITING_APPROVAL
        ).aggregate(s=Sum("amount"))["s"]
        or ZERO
    )
    if amount > native - pending:
        raise BusinessRuleViolation(
            f"Only {native - pending} {bank.currency} of customer credit is available to refund.",
            code="insufficient_credit",
        )
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise ValidationError({"reason": "Explain the refund."})
    on = data.get("refund_date") or timezone.localdate()
    refund = Refund.objects.create(
        number=next_number("refund", on, lambda n: Refund.objects.filter(number=n).exists()),
        client_key=key,
        fingerprint=digest,
        customer=customer,
        bank_account=bank,
        refund_date=on,
        currency=bank.currency,
        amount=amount,
        method=data.get("method", "bank_transfer"),
        reference=(data.get("reference") or "")[:120],
        reason=reason[:500],
        status=Refund.Status.AWAITING_APPROVAL,
        created_by=request.user,
    )
    rate, _ = rate_for(bank.currency, on, company.base_currency)
    if _policy_applies("refund.pay", convert(amount, rate, company.base_currency)):
        refund.approval = approvals.submit(
            request,
            action="refund.pay",
            subject_key=f"refund:{refund.pk}",
            title=f"Refund {refund.number} — {bank.currency} {amount}"[:200],
            payload=strings({"refund_id": refund.pk, "amount": amount}),
            reason=refund.reason,
        )
        refund.save(update_fields=["approval"])
        record("billing.refund_requested", request=request, target=refund)
        return refund
    return _pay_refund(request, refund, request.user)


def execute_refund(request, approval, approver):
    refund = Refund.objects.select_for_update().get(pk=approval.payload["refund_id"])
    if refund.status != Refund.Status.AWAITING_APPROVAL:
        raise BusinessRuleViolation("The refund is no longer awaiting approval.")
    _pay_refund(request, refund, approver)
    return f"refund:{refund.pk}"


def sync_refund(refund):
    if (
        refund.status == Refund.Status.AWAITING_APPROVAL
        and refund.approval_id
        and refund.approval.status in ("rejected", "cancelled")
    ):
        refund.status = Refund.Status.REJECTED
        refund.save(update_fields=["status"])
    return refund


def _pay_refund(request, refund, actor):
    authority = authorize(actor, "customer_refund", "pay")
    company = lock_company()
    native, base_balance = credit_balance(refund.customer_id, refund.currency, lock=True)
    carrying = _carrying(refund.amount, native, base_balance, refund.currency)
    bank = BankAccount.objects.select_for_update().get(pk=refund.bank_account_id)
    rate, source = rate_for(refund.currency, refund.refund_date, company.base_currency)
    raw = [
        {
            "account_id": common.control("customer_credit").pk,
            "currency": refund.currency,
            "debit": str(refund.amount),
            "base_debit": str(carrying),
            "exchange_rate": str(rate),
            "rate_source": "Customer credit carrying value",
            "valuation": "historical",
            "description": "Customer credit refunded",
            "dimensions": {"customer": refund.customer_id},
        },
        {
            "account_id": bank.gl_account_id,
            "currency": refund.currency,
            "credit": str(refund.amount),
            "exchange_rate": str(rate),
            "rate_source": source,
            "description": f"Refund {refund.number}",
        },
    ]
    raw, built, _, _ = posting.balance_with_fx(raw, company, refund.refund_date)
    refund.journal = posting.post_journal(
        actor=actor,
        authority=authority,
        request_context=request,
        posting_key=common.posting_key("refund", refund.pk, "pay"),
        source_type="customer_refund",
        source_id=refund.pk,
        source_action="pay",
        posting_date=refund.refund_date,
        description=f"Customer refund {refund.number} — {refund.customer.name}"[:500],
        lines=raw,
        reason=refund.reason,
    )
    refund.base_amount = built[1].base_credit
    refund.status = Refund.Status.PAID
    refund.save()
    CustomerCreditMovement.objects.create(
        customer=refund.customer,
        currency=refund.currency,
        amount=-refund.amount,
        base_amount=-carrying,
        kind="refund",
        refund=refund,
    )
    record("billing.refund_paid", request=request, target=refund, after={"amount": refund.amount})
    return refund
