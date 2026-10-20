"""Client payments: record → verify (post) / reject / cancel, receipts and reversal.

A recorded payment has no ledger effect. Verification is a separate decision (never by
the recorder unless the client-payments policy allows self-approval) that posts
Dr bank / Cr receivable at each invoice's historical base value, the realized FX
difference, and Cr customer credit for any unapplied remainder; the official money
receipt is numbered in the same transaction and rendered after commit.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounting.money import ZERO, convert, money, strings
from apps.accounting.services import posting
from apps.accounting.services.adapters import authorize
from apps.accounting.services.setup import lock_company, rate_for
from apps.accounts.authorization import require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.banking.models import BankAccount
from apps.company.services import next_number
from apps.core.exceptions import BusinessRuleViolation
from apps.sales.models import Customer

from ..models import (
    CustomerCreditMovement,
    CustomerPayment,
    Invoice,
    MoneyReceipt,
    PaymentAllocation,
)
from . import common
from .invoices import reserved, settle_status

Status = CustomerPayment.Status
OPEN = (Status.PENDING, Status.AWAITING_APPROVAL)


def _key(key):
    if not isinstance(key, str) or not 8 <= len(key) <= 160:
        raise ValidationError({"posting_key": "Send a stable Idempotency-Key of 8–160 characters."})
    return key


def locked(pk) -> CustomerPayment:
    payment = CustomerPayment.objects.select_for_update().filter(pk=pk).first()
    if payment is None:
        raise NotFound()
    return payment


def sync_approval(payment):
    if payment.status == Status.AWAITING_APPROVAL and payment.approval_id:
        decision = payment.approval.status
        if decision == "rejected":
            payment.status = Status.REJECTED
            payment.decision_reason = payment.approval.decision_reason
            payment.decided_by, payment.decided_at = (
                payment.approval.reviewed_by,
                payment.approval.reviewed_at,
            )
            payment.save()
        elif decision == "cancelled":
            payment.status = Status.PENDING
            payment.save(update_fields=["status"])
    return payment


def _locked_invoices(ids):
    invoices = {
        i.pk: i for i in Invoice.objects.select_for_update().filter(pk__in=ids).order_by("pk")
    }
    if len(invoices) != len(set(ids)):
        raise ValidationError({"allocations": "An allocated invoice does not exist."})
    return invoices


@transaction.atomic
def record_payment(request, data, key):
    require(request.user, "payments.record")
    lock_company()
    key = _key(key)
    digest = posting.fingerprint({k: v for k, v in data.items()})
    existing = CustomerPayment.objects.filter(client_key=key).first()
    if existing:
        if existing.fingerprint != digest:
            raise BusinessRuleViolation(
                "The idempotency key was used for a different payment.", code="idempotency_conflict"
            )
        return existing
    customer = Customer.objects.filter(pk=data.get("customer_id"), is_active=True).first()
    if customer is None:
        raise ValidationError({"customer_id": "Select an active customer."})
    bank = BankAccount.objects.filter(pk=data.get("bank_account_id"), is_active=True).first()
    if bank is None:
        raise ValidationError(
            {"bank_account_id": "Select the active bank or cash account received into."}
        )
    amount = common.positive(money(data.get("amount"), bank.currency))
    on = data.get("payment_date") or timezone.localdate()
    if on > timezone.localdate():
        raise ValidationError({"payment_date": "A payment cannot be dated in the future."})
    rows = data.get("allocations") or []
    invoices = _locked_invoices([r.get("invoice_id") for r in rows])
    allocated = ZERO
    planned = []
    for row in rows:
        invoice = invoices[row["invoice_id"]]
        value = common.positive(money(row.get("amount"), bank.currency, "allocations.amount"))
        if invoice.customer_id != customer.pk:
            raise ValidationError({"allocations": f"{invoice} belongs to another customer."})
        if invoice.status not in ("issued", "partially_paid"):
            raise ValidationError({"allocations": f"{invoice} is not open for payment."})
        if invoice.currency != bank.currency:
            raise ValidationError(
                {
                    "allocations": (
                        f"{invoice} is in {invoice.currency}; "
                        f"receive it into a {invoice.currency} account."
                    )
                }
            )
        if value > invoice.outstanding - reserved(invoice):
            raise BusinessRuleViolation(
                f"{invoice} has {invoice.outstanding - reserved(invoice)} open "
                "after pending payments.",
                code="overallocation",
            )
        allocated += value
        planned.append((invoice, value))
    if allocated > amount:
        raise ValidationError({"allocations": "Allocations exceed the amount received."})
    if amount > allocated and not data.get("accept_unapplied", False):
        raise ValidationError(
            {
                "accept_unapplied": (
                    "Confirm that the unallocated remainder is held as customer credit."
                )
            }
        )
    payment = CustomerPayment.objects.create(
        number=next_number(
            "payment", on, lambda n: CustomerPayment.objects.filter(number=n).exists()
        ),
        client_key=key,
        fingerprint=digest,
        customer=customer,
        bank_account=bank,
        payment_date=on,
        currency=bank.currency,
        amount=amount,
        unapplied_amount=amount - allocated,
        method=data.get("method", "bank_transfer"),
        reference=(data.get("reference") or "")[:120],
        notes=(data.get("notes") or "")[:1000],
        recorded_by=request.user,
    )
    for invoice, value in planned:
        PaymentAllocation.objects.create(payment=payment, invoice=invoice, amount=value)
    record(
        "billing.payment_recorded",
        request=request,
        target=payment,
        after={"number": payment.number, "amount": amount, "allocated": allocated},
    )
    return payment


def _policy():
    return approvals.policy_for_action("payment.verify")


def _check_decider(user, payment):
    policy = _policy()
    if payment.recorded_by_id == user.pk and not (policy and policy.allow_self_approval):
        raise PermissionDenied("You cannot verify or reject a payment you recorded.")


@transaction.atomic
def verify_payment(request, pk):
    require(request.user, "payments.approve")
    company = lock_company()
    payment = sync_approval(locked(pk))
    if payment.status == Status.VERIFIED:
        return payment
    if payment.status != Status.PENDING:
        raise BusinessRuleViolation(f"This payment is {payment.get_status_display().lower()}.")
    _check_decider(request.user, payment)
    policy = _policy()
    rate, _ = rate_for(payment.currency, payment.payment_date, company.base_currency)
    if (
        policy
        and policy.in_force
        and (
            policy.amount_threshold is None
            or convert(payment.amount, rate, company.base_currency) >= policy.amount_threshold
        )
    ):
        payment.approval = approvals.submit(
            request,
            action="payment.verify",
            subject_key=f"payment:{payment.pk}",
            title=f"Verify payment {payment.number} — {payment.currency} {payment.amount}"[:200],
            payload=strings({"payment_id": payment.pk, "amount": payment.amount}),
        )
        payment.status = Status.AWAITING_APPROVAL
        payment.save()
        record("billing.payment_submitted", request=request, target=payment)
        return payment
    return _post(request, payment, request.user)


def execute_approval(request, approval, approver):
    payment = locked(approval.payload["payment_id"])
    if payment.status != Status.AWAITING_APPROVAL:
        raise BusinessRuleViolation("The payment is no longer awaiting approval.")
    # The approval engine separates requester and approver; the recorder is separated too.
    _check_decider(approver, payment)
    _post(request, payment, approver)
    return f"payment:{payment.pk}"


def _post(request, payment, approver):
    authority = authorize(approver, "customer_payment", "verify")
    company = lock_company()
    base = company.base_currency
    branding = common.published_branding()
    receivable = common.control("receivable")
    allocations = list(payment.allocations.order_by("invoice_id"))
    invoices = _locked_invoices([a.invoice_id for a in allocations])
    bank = BankAccount.objects.select_for_update().get(pk=payment.bank_account_id)
    if not bank.is_active or bank.currency != payment.currency:
        raise BusinessRuleViolation(
            "The receiving bank account is inactive or its currency changed."
        )
    rate, source = rate_for(payment.currency, payment.payment_date, base)
    raw = [
        {
            "account_id": bank.gl_account_id,
            "currency": payment.currency,
            "debit": str(payment.amount),
            "exchange_rate": str(rate),
            "rate_source": source,
            "description": f"Payment {payment.number}",
        }
    ]
    portions = []
    for allocation in allocations:
        invoice = invoices[allocation.invoice_id]
        if invoice.status not in ("issued", "partially_paid"):
            raise BusinessRuleViolation(f"{invoice} is no longer open for payment.")
        if allocation.amount > invoice.outstanding:
            raise BusinessRuleViolation(
                f"{invoice} has only {invoice.outstanding} outstanding; "
                "the payment would over-allocate.",
                code="overallocation",
            )
        portion = common.settlement_base(
            allocation.amount,
            total=invoice.total - invoice.amount_credited,
            base_total=invoice.base_total,
            native_settled=invoice.amount_paid,
            base_settled=invoice.base_settled,
            rate=invoice.exchange_rate,
            base=base,
        )
        portions.append((allocation, invoice, portion))
        raw.append(
            {
                "account_id": receivable.pk,
                "currency": payment.currency,
                "credit": str(allocation.amount),
                "base_credit": str(portion),
                "exchange_rate": str(invoice.exchange_rate),
                "rate_source": f"Historical rate of {invoice.number}",
                "valuation": "historical",
                "description": f"Settles {invoice.number}",
                "dimensions": {"customer": payment.customer_id, "invoice": invoice.pk},
            }
        )
    credit_base = ZERO
    if payment.unapplied_amount:
        credit_base = convert(payment.unapplied_amount, rate, base)
        raw.append(
            {
                "account_id": common.control("customer_credit").pk,
                "currency": payment.currency,
                "credit": str(payment.unapplied_amount),
                "base_credit": str(credit_base),
                "exchange_rate": str(rate),
                "rate_source": source,
                "description": "Unapplied receipt held as customer credit",
                "dimensions": {"customer": payment.customer_id},
            }
        )
    raw, built, _, _ = posting.balance_with_fx(raw, company, payment.payment_date)
    journal = posting.post_journal(
        actor=approver,
        authority=authority,
        request_context=request,
        posting_key=common.posting_key("payment", payment.pk, "verify"),
        source_type="customer_payment",
        source_id=payment.pk,
        source_action="verify",
        posting_date=payment.payment_date,
        description=f"Client payment {payment.number} — {payment.customer.name}"[:500],
        lines=raw,
    )
    for allocation, invoice, portion in portions:
        invoice.amount_paid += allocation.amount
        invoice.base_settled += portion
        settle_status(invoice)
        invoice.save(update_fields=["amount_paid", "base_settled", "status"])
        allocation.base_amount = portion
        allocation.save(update_fields=["base_amount"])
    if payment.unapplied_amount:
        CustomerCreditMovement.objects.create(
            customer=payment.customer,
            currency=payment.currency,
            amount=payment.unapplied_amount,
            base_amount=credit_base,
            kind="unapplied",
            payment=payment,
        )
    payment.status = Status.VERIFIED
    payment.decided_by, payment.decided_at = approver, timezone.now()
    payment.exchange_rate = rate
    payment.base_amount = built[0].base_debit
    payment.journal = journal
    payment.save()
    receipt = _receipt(payment, portions, branding)
    record(
        "billing.payment_verified",
        request=request,
        target=payment,
        after={"journal": journal.number, "receipt": receipt.number},
    )
    return payment


def _receipt(payment, portions, branding):
    today = timezone.localdate()
    number = next_number("receipt", today, lambda n: MoneyReceipt.objects.filter(number=n).exists())
    method = dict(CustomerPayment.METHODS).get(payment.method, payment.method)
    customer = payment.customer
    snapshot = strings(
        {
            "number": number,
            "issue_date": today,
            "payment_number": payment.number,
            "payment_date": payment.payment_date,
            "method": method,
            "reference": payment.reference,
            "bank_account": payment.bank_account.name,
            "amount": payment.amount,
            "unapplied": payment.unapplied_amount,
            "customer": {"code": customer.code, "name": customer.name, "tax_id": customer.tax_id},
            "company": common.company_identity(),
            "format": common.money_format(payment.currency),
            "allocations": [
                {
                    "number": invoice.number,
                    "invoice_total": invoice.total,
                    "amount": allocation.amount,
                    "balance_after": invoice.outstanding,
                }
                for allocation, invoice, _ in portions
            ],
        }
    )
    return MoneyReceipt.objects.create(
        number=number,
        payment=payment,
        issue_date=today,
        branding_version=branding,
        snapshot=snapshot,
        pdf_status="pending",
    )


def verify_and_render(request, pk):
    from apps.documents.services import generate_pdf

    payment = verify_payment(request, pk)
    receipt = MoneyReceipt.objects.filter(payment=payment).first()
    if receipt and receipt.pdf_status != "ready":
        generate_pdf("receipt", receipt.pk)
    payment.refresh_from_db()
    return payment


@transaction.atomic
def reject_payment(request, pk, reason):
    require(request.user, "payments.approve")
    lock_company()
    payment = sync_approval(locked(pk))
    if not reason.strip():
        raise ValidationError({"reason": "Explain why the payment is rejected."})
    if payment.status != Status.PENDING:
        raise BusinessRuleViolation("Only payments pending verification can be rejected.")
    _check_decider(request.user, payment)
    payment.status = Status.REJECTED
    payment.decided_by, payment.decided_at = request.user, timezone.now()
    payment.decision_reason = reason.strip()[:500]
    payment.save()
    record(
        "billing.payment_rejected", request=request, target=payment, reason=payment.decision_reason
    )
    return payment


@transaction.atomic
def cancel_payment(request, pk, reason):
    require(request.user, "payments.record")
    lock_company()
    payment = sync_approval(locked(pk))
    if payment.status != Status.PENDING:
        raise BusinessRuleViolation("Only payments pending verification can be cancelled.")
    payment.status = Status.CANCELLED
    payment.decision_reason = reason.strip()[:500]
    payment.decided_by, payment.decided_at = request.user, timezone.now()
    payment.save()
    record(
        "billing.payment_cancelled", request=request, target=payment, reason=payment.decision_reason
    )
    return payment


@transaction.atomic
def reverse_payment(request, pk, reason, on=None):
    """Reverse a verified payment (e.g. a bounced transfer) with an exact reversal journal."""
    authority = authorize(request.user, "customer_payment", "reverse")
    lock_company()
    payment = locked(pk)
    if not reason.strip():
        raise ValidationError({"reason": "Explain the reversal."})
    if payment.status == Status.REVERSED:
        return payment
    if payment.status != Status.VERIFIED:
        raise BusinessRuleViolation("Only verified payments can be reversed.")
    allocations = list(payment.allocations.order_by("invoice_id"))
    invoices = _locked_invoices([a.invoice_id for a in allocations])
    if payment.unapplied_amount:
        from .credits import credit_balance

        native, _ = credit_balance(payment.customer_id, payment.currency, lock=True)
        if native < payment.unapplied_amount:
            raise BusinessRuleViolation(
                "Part of this payment's customer credit was already used. Reverse those uses first."
            )
    reversal = posting.reverse(
        request,
        payment.journal_id,
        on or timezone.localdate(),
        reason.strip()[:500],
        common.posting_key("payment", payment.pk, "reverse"),
        authority=authority,
    )
    for allocation in allocations:
        invoice = invoices[allocation.invoice_id]
        invoice.amount_paid -= allocation.amount
        invoice.base_settled -= allocation.base_amount
        settle_status(invoice)
        invoice.save(update_fields=["amount_paid", "base_settled", "status"])
    if payment.unapplied_amount:
        original = CustomerCreditMovement.objects.get(payment=payment, kind="unapplied")
        CustomerCreditMovement.objects.create(
            customer=payment.customer,
            currency=payment.currency,
            amount=-original.amount,
            base_amount=-original.base_amount,
            kind="reversal",
            payment=payment,
        )
    payment.status = Status.REVERSED
    payment.reversal_journal = reversal
    payment.decision_reason = reason.strip()[:500]
    payment.save()
    MoneyReceipt.objects.filter(payment=payment).update(status=MoneyReceipt.Status.CANCELLED)
    record(
        "billing.payment_reversed", request=request, target=payment, reason=payment.decision_reason
    )
    return payment
