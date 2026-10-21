"""Vendors, vendor bills and expenses (the payable and expense adapters).

Bills: Dr expense/asset lines + Dr recoverable input tax / Cr payable.
Expenses paid now: Dr expense + input tax / Cr bank (no payable, so never paid twice).
Accrued expenses: Dr expense + input tax / Cr payable, settled by vendor payments.
"""

import re
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounting.money import convert, decimal, money, strings
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
from apps.sales import calculation
from apps.sales.models import Project
from apps.sales.services import enabled_currency, next_code

from ..models import Expense, Vendor, VendorBill, VendorBillLine

VENDOR_FIELDS = (
    "name",
    "contact_name",
    "email",
    "phone",
    "address",
    "country",
    "currency",
    "payment_terms_days",
    "tax_id",
    "website",
    "notes",
    "is_active",
)


def normalize_reference(value: str) -> str:
    """Vendor invoice numbers compare without case, spaces or punctuation."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())[:80]


@transaction.atomic
def save_vendor(request, data, pk=None):
    require(request.user, "vendors.manage")
    lock_company()
    vendor = (
        Vendor.objects.select_for_update().filter(pk=pk).first()
        if pk
        else Vendor(created_by=request.user)
    )
    if pk and vendor is None:
        raise NotFound()
    if (
        pk
        and "currency" in data
        and data["currency"] != vendor.currency
        and (
            vendor.bills.exclude(status="draft").exists()
            or vendor.expenses.exclude(status="draft").exists()
        )
    ):
        raise BusinessRuleViolation(
            "The vendor currency is locked by posted documents.", code="currency_locked"
        )
    for field in VENDOR_FIELDS:
        if field in data:
            setattr(vendor, field, data[field])
    if "default_account_id" in data:
        vendor.default_account = (
            common.posting_account(data["default_account_id"], kind="expense")
            if data["default_account_id"]
            else None
        )
    if not vendor.name.strip():
        raise ValidationError({"name": "Enter the vendor's name."})
    enabled_currency(vendor.currency)
    if not vendor.code:
        vendor.code = next_code("vendor", "VEN", Vendor)
    vendor.full_clean()
    vendor.save()
    record(
        "purchasing.vendor_updated" if pk else "purchasing.vendor_created",
        request=request,
        target=vendor,
        after={f: getattr(vendor, f) for f in VENDOR_FIELDS},
    )
    return vendor


def _policy_applies(currency, on, total):
    policy = approvals.policy_for_action("vendor_bill.post")
    if not (policy and policy.in_force):
        return False
    if policy.amount_threshold is None:
        return True
    base = common.base_currency()
    rate, _ = rate_for(currency, on, base)
    return convert(total, rate, base) >= policy.amount_threshold


def _project(data, obj):
    if "project_id" in data:
        obj.project = (
            Project.objects.filter(pk=data["project_id"]).first() if data["project_id"] else None
        )


# ---------------------------------------------------------------- vendor bills


@transaction.atomic
def save_bill(request, data, pk=None):
    require(request.user, "bills.manage")
    lock_company()
    bill = (
        VendorBill.objects.select_for_update().filter(pk=pk).first()
        if pk
        else VendorBill(created_by=request.user)
    )
    if pk:
        if bill is None:
            raise NotFound()
        _sync(bill)
        if bill.status != VendorBill.Status.DRAFT:
            raise BusinessRuleViolation("Only draft bills can be edited.")
        if data.get("revision") != bill.revision:
            raise BusinessRuleViolation(
                "This bill changed. Reload before saving.", code="stale_revision"
            )
        bill.revision += 1
    for field in (
        "vendor_reference",
        "bill_date",
        "due_date",
        "currency",
        "prices_include_tax",
        "notes",
    ):
        if field in data:
            setattr(bill, field, data[field])
    if "vendor_id" in data:
        bill.vendor = Vendor.objects.filter(pk=data["vendor_id"], is_active=True).first()
    if bill.vendor_id is None:
        raise ValidationError({"vendor_id": "Select an active vendor."})
    _project(data, bill)
    if not (bill.vendor_reference or "").strip():
        raise ValidationError({"vendor_reference": "Enter the vendor's invoice number."})
    bill.normalized_reference = normalize_reference(bill.vendor_reference)
    duplicate = (
        VendorBill.objects.filter(
            vendor=bill.vendor, normalized_reference=bill.normalized_reference
        )
        .exclude(status__in=("void", "cancelled"))
        .exclude(pk=bill.pk)
        .first()
    )
    if duplicate:
        raise BusinessRuleViolation(
            f"Vendor invoice {bill.vendor_reference} is already recorded as "
            f"{duplicate.number or 'a draft bill'}.",
            code="duplicate_vendor_invoice",
        )
    if not bill.bill_date:
        raise ValidationError({"bill_date": "Enter the bill date."})
    bill.due_date = bill.due_date or bill.bill_date + timedelta(days=bill.vendor.payment_terms_days)
    bill.currency = bill.currency or bill.vendor.currency
    enabled_currency(bill.currency)
    bill.save()
    if "lines" in data or not pk:
        _bill_lines(bill, data.get("lines") or [])
        bill.save()
    record(
        "purchasing.bill_updated" if pk else "purchasing.bill_created",
        request=request,
        target=bill,
        after={"vendor": bill.vendor.code, "reference": bill.vendor_reference, "total": bill.total},
    )
    return bill


def _bill_lines(bill, rows):
    if not rows:
        raise ValidationError({"lines": "Add at least one line."})
    accounts = [
        common.posting_account(
            row.get("account_id"), kind="expense", fallback=bill.vendor.default_account
        )
        for row in rows
    ]
    result = calculation.calculate(
        currency=bill.currency,
        on=bill.bill_date,
        lines=rows,
        prices_include_tax=bill.prices_include_tax,
    )
    bill.lines.all().delete()
    for row, account, line in zip(rows, accounts, result["lines"], strict=True):
        description = str(row.get("description") or "").strip()[:500]
        if not description:
            raise ValidationError({"lines": "Describe every line."})
        VendorBillLine.objects.create(
            bill=bill,
            position=line["position"],
            description=description,
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            discount_type=row.get("discount_type", "percent"),
            discount_value=decimal(row.get("discount_value") or "0", "discount_value", 6),
            tax_code_id=line["tax_code_id"],
            account=account,
            subtotal=line["subtotal"],
            line_discount=line["line_discount"],
            taxable=line["taxable"],
            tax=line["tax"],
            total=line["total"],
            tax_rate=line["tax_rate"],
            tax_revision_id=line["tax_revision_id"],
        )
    for field in ("subtotal", "line_discount", "taxable", "tax", "total"):
        setattr(bill, field, result[field])


def _sync(doc):
    if (
        doc.status == "awaiting_approval"
        and doc.approval_id
        and doc.approval.status in ("rejected", "cancelled")
    ):
        doc.status = "draft"
        doc.save(update_fields=["status"])
    return doc


def _debits(rows, currency, rate, base):
    """Expense/asset per account and input tax per revision, base allocated exactly."""
    debits = {}
    for account_id, revision, taxable, tax in rows:
        if taxable:
            debits[(account_id, None)] = debits.get((account_id, None), 0) + taxable
        if tax:
            key = (revision.input_account_id, revision.pk)
            debits[key] = debits.get(key, 0) + tax
    total = sum(debits.values())
    base_total = convert(total, rate, base)
    keys = list(debits)
    bases = calculation.allocate(base_total, [debits[k] for k in keys], base)
    return base_total, [
        {
            "account_id": account_id,
            "currency": currency,
            "debit": str(debits[(account_id, rev)]),
            "base_debit": str(b),
            "exchange_rate": str(rate),
            "rate_source": "Document date rate",
            "valuation": "allocated",
            "tax_revision_id": rev,
            "description": "Recoverable input tax" if rev else "Expense",
        }
        for (account_id, rev), b in zip(keys, bases, strict=True)
    ]


@transaction.atomic
def post_bill(request, pk):
    require(request.user, "bills.manage")
    lock_company()
    bill = VendorBill.objects.select_for_update().filter(pk=pk).first()
    if bill is None:
        raise NotFound()
    _sync(bill)
    if bill.number:
        return bill
    if bill.status == VendorBill.Status.AWAITING_APPROVAL:
        raise BusinessRuleViolation("This bill is waiting for approval.", code="approval_pending")
    if bill.total <= 0:
        raise ValidationError({"lines": "A bill total must be positive."})
    if _policy_applies(bill.currency, bill.bill_date, bill.total):
        bill.approval = approvals.submit(
            request,
            action="vendor_bill.post",
            subject_key=f"bill:{bill.pk}",
            title=f"Post bill {bill.vendor_reference} — {bill.vendor.name}"[:200],
            payload=strings({"bill_id": bill.pk, "revision": bill.revision, "total": bill.total}),
        )
        bill.status = VendorBill.Status.AWAITING_APPROVAL
        bill.save()
        return bill
    return _post_bill(request, bill, request.user)


def execute_bill(request, approval, approver):
    bill = VendorBill.objects.select_for_update().get(pk=approval.payload["bill_id"])
    if (
        bill.status != VendorBill.Status.AWAITING_APPROVAL
        or bill.revision != approval.payload["revision"]
    ):
        raise BusinessRuleViolation("The bill changed after it was submitted for approval.")
    _post_bill(request, bill, approver)
    return f"bill:{bill.pk}"


def _post_bill(request, bill, actor):
    authority = authorize(actor, "vendor_bill", "post")
    company = lock_company()
    base = company.base_currency
    payable = common.control("payable")
    rate, source = rate_for(bill.currency, bill.bill_date, base)
    rows = [
        (line.account_id, line.tax_revision, line.taxable, line.tax)
        for line in bill.lines.select_related("tax_revision")
    ]
    base_total, raw = _debits(rows, bill.currency, rate, base)
    raw.append(
        {
            "account_id": payable.pk,
            "currency": bill.currency,
            "credit": str(bill.total),
            "base_credit": str(base_total),
            "exchange_rate": str(rate),
            "rate_source": source,
            "description": f"Payable — {bill.vendor.name}",
            "dimensions": {"vendor": bill.vendor_id, "bill": bill.pk},
        }
    )
    number = next_number(
        "vendor_bill", bill.bill_date, lambda n: VendorBill.objects.filter(number=n).exists()
    )
    journal = posting.post_journal(
        actor=actor,
        authority=authority,
        request_context=request,
        posting_key=common.posting_key("bill", bill.pk, "post"),
        source_type="vendor_bill",
        source_id=bill.pk,
        source_action="post",
        posting_date=bill.bill_date,
        description=f"Bill {number} · {bill.vendor_reference} — {bill.vendor.name}"[:500],
        lines=raw,
    )
    bill.number, bill.journal = number, journal
    bill.exchange_rate, bill.base_total = rate, base_total
    bill.status = VendorBill.Status.POSTED
    bill.posted_by, bill.posted_at = actor, timezone.now()
    bill.save()
    record(
        "purchasing.bill_posted",
        request=request,
        target=bill,
        after={"number": number, "journal": journal.number},
    )
    return bill


@transaction.atomic
def void_bill(request, pk, reason, on=None):
    authority = authorize(request.user, "vendor_bill", "void")
    lock_company()
    bill = VendorBill.objects.select_for_update().filter(pk=pk).first()
    if bill is None:
        raise NotFound()
    if not reason.strip():
        raise ValidationError({"reason": "Explain why the bill is voided."})
    if bill.status == VendorBill.Status.VOID:
        return bill
    if bill.status != VendorBill.Status.POSTED or bill.amount_paid:
        raise BusinessRuleViolation("Only posted, unpaid bills can be voided.")
    bill.void_journal = posting.reverse(
        request,
        bill.journal_id,
        on or timezone.localdate(),
        reason.strip()[:500],
        common.posting_key("bill", bill.pk, "void"),
        authority=authority,
    )
    bill.status = VendorBill.Status.VOID
    bill.void_reason = reason.strip()[:500]
    bill.save()
    record("purchasing.bill_voided", request=request, target=bill, reason=bill.void_reason)
    return bill


@transaction.atomic
def cancel_bill(request, pk):
    require(request.user, "bills.manage")
    bill = VendorBill.objects.select_for_update().filter(pk=pk).first()
    if bill is None:
        raise NotFound()
    _sync(bill)
    if bill.status != VendorBill.Status.DRAFT:
        raise BusinessRuleViolation("Only draft bills can be cancelled.")
    bill.status = VendorBill.Status.CANCELLED
    bill.save(update_fields=["status"])
    record("purchasing.bill_cancelled", request=request, target=bill)
    return bill


# ---------------------------------------------------------------- expenses

EXPENSE_FIELDS = (
    "expense_date",
    "due_date",
    "description",
    "currency",
    "prices_include_tax",
    "payment_mode",
    "method",
    "reference",
    "notes",
)


@transaction.atomic
def save_expense(request, data, pk=None, *, schedule=None):
    require(request.user, "expenses.manage")
    lock_company()
    expense = (
        Expense.objects.select_for_update().filter(pk=pk).first()
        if pk
        else Expense(created_by=request.user)
    )
    if pk:
        if expense is None:
            raise NotFound()
        if hasattr(expense, "founder_funding"):
            raise BusinessRuleViolation(
                "This expense is owned by Founder Finance. Reject and record a corrected "
                "founder transaction instead of changing its source."
            )
        _sync(expense)
        if expense.status != Expense.Status.DRAFT:
            raise BusinessRuleViolation("Only draft expenses can be edited.")
        if data.get("revision") != expense.revision:
            raise BusinessRuleViolation(
                "This expense changed. Reload before saving.", code="stale_revision"
            )
        expense.revision += 1
    if data.get("paid_by", "company") != "company":
        raise ValidationError({"paid_by": "Record founder funding through Founder Finance."})
    for field in EXPENSE_FIELDS:
        if field in data:
            setattr(expense, field, data[field])
    if "vendor_id" in data:
        expense.vendor = (
            Vendor.objects.filter(pk=data["vendor_id"]).first() if data["vendor_id"] else None
        )
    _project(data, expense)
    if not (expense.description or "").strip():
        raise ValidationError({"description": "Describe the expense."})
    expense.account = common.posting_account(
        data.get("account_id", expense.account_id),
        kind="expense",
        fallback=expense.vendor.default_account if expense.vendor else None,
    )
    if expense.payment_mode == Expense.Mode.PAID:
        bank = BankAccount.objects.filter(
            pk=data.get("bank_account_id", expense.bank_account_id), is_active=True
        ).first()
        if bank is None:
            raise ValidationError({"bank_account_id": "Choose the bank or cash account that paid."})
        expense.bank_account = bank
        expense.currency = bank.currency
        expense.due_date = None
    elif expense.payment_mode == Expense.Mode.ACCRUED:
        if expense.vendor is None:
            raise ValidationError({"vendor_id": "Accrued expenses are payable to a vendor."})
        expense.bank_account = None
        expense.currency = expense.currency or expense.vendor.currency
        expense.due_date = expense.due_date or expense.expense_date + timedelta(
            days=expense.vendor.payment_terms_days
        )
    elif expense.payment_mode == Expense.Mode.FOUNDER:
        require(request.user, "founder.transactions.manage")
        expense.bank_account = None
        expense.due_date = None
    else:
        raise ValidationError({"payment_mode": "Choose paid now or accrued."})
    enabled_currency(expense.currency)
    expense.entered_amount = common.positive(
        money(data.get("amount", expense.entered_amount), expense.currency, "amount")
    )
    if "tax_code_id" in data:
        expense.tax_code_id = data["tax_code_id"]
    result = calculation.calculate(
        currency=expense.currency,
        on=expense.expense_date,
        prices_include_tax=expense.prices_include_tax,
        lines=[
            {
                "quantity": "1",
                "unit_price": str(expense.entered_amount),
                "tax_code_id": expense.tax_code_id,
            }
        ],
    )
    line = result["lines"][0]
    expense.taxable, expense.tax, expense.total = line["taxable"], line["tax"], line["total"]
    expense.tax_revision_id = line["tax_revision_id"]
    expense.recurring_schedule = schedule or expense.recurring_schedule
    expense.full_clean()
    expense.save()
    record(
        "purchasing.expense_updated" if pk else "purchasing.expense_created",
        request=request,
        target=expense,
        after={
            "description": expense.description,
            "total": expense.total,
            "mode": expense.payment_mode,
        },
    )
    return expense


@transaction.atomic
def post_expense(request, pk):
    require(request.user, "expenses.manage")
    lock_company()
    expense = Expense.objects.select_for_update().filter(pk=pk).first()
    if expense is None:
        raise NotFound()
    _sync(expense)
    if expense.number:
        return expense
    if expense.status == Expense.Status.AWAITING_APPROVAL:
        raise BusinessRuleViolation(
            "This expense is waiting for approval.", code="approval_pending"
        )
    policy = approvals.policy_for_action("expense.post")
    base = common.base_currency()
    rate, _ = rate_for(expense.currency, expense.expense_date, base)
    if (
        policy
        and policy.in_force
        and (
            policy.amount_threshold is None
            or convert(expense.total, rate, base) >= policy.amount_threshold
        )
    ):
        expense.approval = approvals.submit(
            request,
            action="expense.post",
            subject_key=f"expense:{expense.pk}",
            title=f"Post expense — {expense.description}"[:200],
            payload=strings(
                {"expense_id": expense.pk, "revision": expense.revision, "total": expense.total}
            ),
        )
        expense.status = Expense.Status.AWAITING_APPROVAL
        expense.save()
        return expense
    return _post_expense(request, expense, request.user)


def execute_expense(request, approval, approver):
    expense = Expense.objects.select_for_update().get(pk=approval.payload["expense_id"])
    if (
        expense.status != Expense.Status.AWAITING_APPROVAL
        or expense.revision != approval.payload["revision"]
    ):
        raise BusinessRuleViolation("The expense changed after it was submitted for approval.")
    _post_expense(request, expense, approver)
    return f"expense:{expense.pk}"


def _post_expense(request, expense, actor):
    if expense.payment_mode == Expense.Mode.FOUNDER:
        raise BusinessRuleViolation("Verify and post this expense through Founder Finance.")
    authority = authorize(actor, "expense", "post")
    company = lock_company()
    base = company.base_currency
    rate, source = rate_for(expense.currency, expense.expense_date, base)
    base_total, raw = _debits(
        [(expense.account_id, expense.tax_revision, expense.taxable, expense.tax)],
        expense.currency,
        rate,
        base,
    )
    if expense.payment_mode == Expense.Mode.PAID:
        bank = BankAccount.objects.select_for_update().get(pk=expense.bank_account_id)
        if not bank.is_active or bank.currency != expense.currency:
            raise BusinessRuleViolation("The paying account is inactive or its currency changed.")
        raw.append(
            {
                "account_id": bank.gl_account_id,
                "currency": expense.currency,
                "credit": str(expense.total),
                "exchange_rate": str(rate),
                "rate_source": source,
                "description": expense.description[:300],
            }
        )
        # Foreign cash leaves at its carrying value; the difference is realized FX.
        raw, built, _, _ = posting.balance_with_fx(raw, company, expense.expense_date)
    else:
        raw.append(
            {
                "account_id": common.control("payable").pk,
                "currency": expense.currency,
                "credit": str(expense.total),
                "base_credit": str(base_total),
                "exchange_rate": str(rate),
                "rate_source": source,
                "description": f"Payable — {expense.vendor.name}",
                "dimensions": {"vendor": expense.vendor_id, "expense": expense.pk},
            }
        )
    number = next_number(
        "expense", expense.expense_date, lambda n: Expense.objects.filter(number=n).exists()
    )
    journal = posting.post_journal(
        actor=actor,
        authority=authority,
        request_context=request,
        posting_key=common.posting_key("expense", expense.pk, "post"),
        source_type="expense",
        source_id=expense.pk,
        source_action="post",
        posting_date=expense.expense_date,
        description=f"Expense {number} — {expense.description}"[:500],
        lines=raw,
    )
    expense.number, expense.journal = number, journal
    expense.exchange_rate, expense.base_total = rate, base_total
    expense.status = (
        Expense.Status.PAID if expense.payment_mode == Expense.Mode.PAID else Expense.Status.POSTED
    )
    expense.posted_by, expense.posted_at = actor, timezone.now()
    expense.save()
    record(
        "purchasing.expense_posted",
        request=request,
        target=expense,
        after={"number": number, "journal": journal.number},
    )
    return expense


@transaction.atomic
def void_expense(request, pk, reason, on=None):
    authority = authorize(request.user, "expense", "void")
    lock_company()
    expense = Expense.objects.select_for_update().filter(pk=pk).first()
    if expense is None:
        raise NotFound()
    if not reason.strip():
        raise ValidationError({"reason": "Explain why the expense is voided."})
    if expense.status == Expense.Status.VOID:
        return expense
    if expense.payment_mode == Expense.Mode.FOUNDER:
        raise BusinessRuleViolation(
            "Reverse the owning founder transaction through Founder Finance."
        )
    from apps.founders.services.planning import active_consumptions

    if (
        active_consumptions().filter(expense=expense).exists()
        or expense.company_funding_coverage.filter(status="consumed").exists()
    ):
        raise BusinessRuleViolation(
            "Release the retained funding allocations with a reason before voiding this expense."
        )
    if not expense.number or expense.amount_paid:
        raise BusinessRuleViolation("Only posted expenses without vendor payments can be voided.")
    expense.void_journal = posting.reverse(
        request,
        expense.journal_id,
        on or timezone.localdate(),
        reason.strip()[:500],
        common.posting_key("expense", expense.pk, "void"),
        authority=authority,
    )
    expense.status = Expense.Status.VOID
    expense.void_reason = reason.strip()[:500]
    expense.save()
    record("purchasing.expense_voided", request=request, target=expense, reason=expense.void_reason)
    return expense


@transaction.atomic
def cancel_expense(request, pk):
    require(request.user, "expenses.manage")
    expense = Expense.objects.select_for_update().filter(pk=pk).first()
    if expense is None:
        raise NotFound()
    if hasattr(expense, "founder_funding") and expense.founder_funding.status != "rejected":
        raise BusinessRuleViolation(
            "Reject the owning founder transaction before cancelling its draft."
        )
    _sync(expense)
    if expense.status != Expense.Status.DRAFT:
        raise BusinessRuleViolation("Only draft expenses can be cancelled.")
    expense.status = Expense.Status.CANCELLED
    expense.save(update_fields=["status"])
    record("purchasing.expense_cancelled", request=request, target=expense)
    return expense
