"""Client invoices: drafts, approval, issuance (the receivable adapter) and voiding.

Lock order: company → approval policy/request → invoice (and sales order) rows →
journal/period/accounts (inside ``post_journal``).
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounting.money import ZERO, convert, decimal, strings
from apps.accounting.services import posting
from apps.accounting.services.adapters import authorize
from apps.accounting.services.setup import lock_company, rate_for
from apps.accounts.authorization import require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.company.services import next_number
from apps.core.exceptions import BusinessRuleViolation
from apps.sales import calculation
from apps.sales.models import BillingItem, Customer, Milestone, Project, SalesOrder, SalesOrderLine
from apps.sales.services import enabled_currency, order_invoiced_quantities, refresh_order_status

from ..models import Invoice, InvoiceLine, PaymentAllocation
from . import common

HEADER = (
    "issue_date",
    "due_date",
    "currency",
    "prices_include_tax",
    "discount_type",
    "reference",
    "notes",
)
EDITABLE = (Invoice.Status.DRAFT, Invoice.Status.APPROVED)


def locked(pk) -> Invoice:
    invoice = Invoice.objects.select_for_update().filter(pk=pk).first()
    if invoice is None:
        raise NotFound()
    return invoice


def sync_approval(invoice: Invoice) -> Invoice:
    """A rejected or withdrawn approval request returns the invoice to draft."""
    if (
        invoice.status == Invoice.Status.PENDING_APPROVAL
        and invoice.approval_id
        and invoice.approval.status in ("rejected", "cancelled")
    ):
        invoice.status = Invoice.Status.DRAFT
        invoice.save(update_fields=["status"])
    return invoice


def _line_payload(invoice, rows):
    payload = []
    for index, row in enumerate(rows, 1):
        item = (
            BillingItem.objects.filter(pk=row.get("item_id")).first()
            if row.get("item_id")
            else None
        )
        if row.get("item_id") and (item is None or not item.is_active):
            raise ValidationError({f"lines.{index}.item_id": "Choose an active billing item."})
        order_line = None
        if row.get("sales_order_line_id"):
            order_line = SalesOrderLine.objects.filter(
                pk=row["sales_order_line_id"], order_id=invoice.sales_order_id
            ).first()
            if order_line is None:
                raise ValidationError(
                    {
                        f"lines.{index}.sales_order_line_id": (
                            "The order line belongs to another order."
                        )
                    }
                )
        account = common.posting_account(
            row.get("revenue_account_id"),
            kind="revenue",
            fallback=item.revenue_account if item else None,
        )
        description = str(row.get("description") or (item.name if item else "")).strip()[:500]
        if not description:
            raise ValidationError({f"lines.{index}.description": "Describe every line."})
        payload.append(
            {
                "item": item,
                "sales_order_line": order_line,
                "description": description,
                "quantity": row.get("quantity", "1"),
                "unit_price": row.get("unit_price", item.unit_price if item else "0"),
                "discount_type": row.get("discount_type", "percent"),
                "discount_value": row.get("discount_value", "0"),
                "tax_code_id": row.get("tax_code_id", item.tax_code_id if item else None),
                "revenue_account": account,
            }
        )
    return payload


def _calculate(invoice, payload):
    return calculation.calculate(
        currency=invoice.currency,
        on=invoice.issue_date,
        lines=payload,
        prices_include_tax=invoice.prices_include_tax,
        discount_type=invoice.discount_type,
        discount_value=invoice.discount_value,
    )


def _store_lines(invoice, payload, result):
    invoice.lines.all().delete()
    for p, line in zip(payload, result["lines"], strict=True):
        InvoiceLine.objects.create(
            invoice=invoice,
            position=line["position"],
            item=p["item"],
            sales_order_line=p["sales_order_line"],
            description=p["description"],
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            discount_type=p["discount_type"],
            discount_value=decimal(p["discount_value"], "discount_value", 6),
            tax_code_id=line["tax_code_id"] or p["tax_code_id"],
            revenue_account=p["revenue_account"],
            subtotal=line["subtotal"],
            line_discount=line["line_discount"],
            document_discount=line["document_discount"],
            taxable=line["taxable"],
            tax=line["tax"],
            total=line["total"],
            tax_rate=line["tax_rate"],
            tax_revision_id=line["tax_revision_id"],
        )
    for field in ("subtotal", "line_discount", "document_discount", "taxable", "tax", "total"):
        setattr(invoice, field, result[field])


@transaction.atomic
def save_invoice(request, data, pk=None, *, schedule=None):
    require(request.user, "invoices.create")
    lock_company()
    invoice = locked(pk) if pk else Invoice(created_by=request.user)
    if pk:
        sync_approval(invoice)
        if invoice.status not in EDITABLE:
            raise BusinessRuleViolation(
                "Only draft invoices can be edited. "
                "Issued invoices are corrected with credit notes."
            )
        if data.get("revision") != invoice.revision:
            raise BusinessRuleViolation(
                "This invoice changed. Reload before saving.", code="stale_revision"
            )
        invoice.revision += 1
        # Any edit invalidates an earlier approval.
        invoice.status, invoice.approved_by, invoice.approved_at = Invoice.Status.DRAFT, None, None
    for field in HEADER:
        if field in data:
            setattr(invoice, field, data[field])
    if "discount_value" in data:
        invoice.discount_value = decimal(data["discount_value"], "discount_value", 6)
    if "customer_id" in data:
        invoice.customer = Customer.objects.filter(pk=data["customer_id"]).first()
    if invoice.customer_id is None or not invoice.customer.is_active:
        raise ValidationError({"customer_id": "Select an active customer."})
    customer = invoice.customer
    if not invoice.issue_date:
        raise ValidationError({"issue_date": "Enter the invoice date."})
    if not invoice.due_date:
        invoice.due_date = invoice.issue_date + timedelta(days=customer.payment_terms_days)
    if invoice.due_date < invoice.issue_date:
        raise ValidationError({"due_date": "The due date cannot precede the invoice date."})
    invoice.currency = invoice.currency or customer.currency
    enabled_currency(invoice.currency)
    for key, model in (
        ("project_id", Project),
        ("milestone_id", Milestone),
        ("sales_order_id", SalesOrder),
    ):
        if key in data:
            setattr(
                invoice,
                key.removesuffix("_id"),
                model.objects.filter(pk=data[key]).first() if data[key] else None,
            )
    if invoice.project and invoice.project.customer_id != customer.pk:
        raise ValidationError({"project_id": "The project belongs to another customer."})
    if invoice.milestone:
        if invoice.project_id and invoice.milestone.project_id != invoice.project_id:
            raise ValidationError({"milestone_id": "The milestone belongs to another project."})
        invoice.project = invoice.milestone.project
        if invoice.project.customer_id != customer.pk:
            raise ValidationError({"milestone_id": "The milestone belongs to another customer."})
        if invoice.currency != invoice.project.currency:
            raise ValidationError({"currency": "Milestone invoices use the project currency."})
        taken = Invoice.objects.filter(milestone=invoice.milestone).exclude(
            status__in=("void", "cancelled")
        )
        if taken.exclude(pk=invoice.pk).exists():
            raise BusinessRuleViolation(
                "This milestone already has an invoice.", code="milestone_invoiced"
            )
    if invoice.sales_order:
        order = invoice.sales_order
        if order.customer_id != customer.pk:
            raise ValidationError(
                {"sales_order_id": "The sales order belongs to another customer."}
            )
        if order.status not in ("confirmed", "partially_invoiced"):
            raise ValidationError(
                {"sales_order_id": "Only confirmed sales orders can be invoiced."}
            )
        if order.currency != invoice.currency:
            raise ValidationError({"currency": "Order invoices use the order currency."})
    invoice.recurring_schedule = schedule or invoice.recurring_schedule
    rows = data.get("lines")
    if rows is None and not pk:
        raise ValidationError({"lines": "Add at least one line."})
    invoice.save()
    if rows is not None:
        payload = _line_payload(invoice, rows)
        result = _calculate(invoice, payload)
        _store_lines(invoice, payload, result)
        invoice.save()
    record(
        "billing.invoice_updated" if pk else "billing.invoice_created",
        request=request,
        target=invoice,
        after={"customer": customer.code, "total": invoice.total, "revision": invoice.revision},
    )
    return invoice


def lines_from_order(order):
    """Remaining (uninvoiced, including drafts) quantities of a confirmed order."""
    taken = order_invoiced_quantities(order, include_drafts=True)
    rows = []
    for line in order.lines.all():
        remaining = line.quantity - taken.get(line.pk, ZERO)
        if remaining > 0:
            rows.append(
                {
                    "sales_order_line_id": line.pk,
                    "item_id": line.item_id,
                    "description": line.description,
                    "quantity": str(remaining),
                    "unit_price": str(line.unit_price),
                    "discount_type": line.discount_type,
                    "discount_value": str(line.discount_value),
                    "tax_code_id": line.tax_code_id,
                    "revenue_account_id": line.item.revenue_account_id if line.item else None,
                }
            )
    if not rows:
        raise BusinessRuleViolation("Every order line is already invoiced or on a draft invoice.")
    return rows


def create_from_order(request, order_pk, data):
    order = SalesOrder.objects.filter(pk=order_pk).first()
    if order is None:
        raise NotFound()
    return save_invoice(
        request,
        {
            "customer_id": order.customer_id,
            "project_id": order.project_id,
            "sales_order_id": order.pk,
            "currency": order.currency,
            "prices_include_tax": order.prices_include_tax,
            "reference": order.customer_reference,
            "issue_date": data.get("issue_date") or timezone.localdate(),
            "lines": lines_from_order(order),
        },
    )


def create_from_milestone(request, milestone_pk, data):
    milestone = Milestone.objects.select_related("project").filter(pk=milestone_pk).first()
    if milestone is None:
        raise NotFound()
    project = milestone.project
    return save_invoice(
        request,
        {
            "customer_id": project.customer_id,
            "project_id": project.pk,
            "milestone_id": milestone.pk,
            "currency": project.currency,
            "issue_date": data.get("issue_date") or timezone.localdate(),
            "lines": [
                {
                    "description": (
                        f"{project.name} — {milestone.name} ({milestone.percent.normalize()}%)"
                    ),
                    "quantity": "1",
                    "unit_price": str(milestone.amount),
                    "tax_code_id": data.get("tax_code_id"),
                    "revenue_account_id": data.get("revenue_account_id"),
                }
            ],
        },
    )


@transaction.atomic
def cancel_draft(request, pk, reason=""):
    require(request.user, "invoices.create")
    lock_company()
    invoice = sync_approval(locked(pk))
    if invoice.status == Invoice.Status.PENDING_APPROVAL:
        raise BusinessRuleViolation("Withdraw the approval request before cancelling this draft.")
    if invoice.status not in EDITABLE:
        raise BusinessRuleViolation("Only drafts can be cancelled. Void or credit issued invoices.")
    invoice.status = Invoice.Status.CANCELLED
    invoice.save(update_fields=["status"])
    record("billing.invoice_cancelled", request=request, target=invoice, reason=reason)
    return invoice


def _base_amount(invoice):
    rate, _ = rate_for(invoice.currency, invoice.issue_date, common.base_currency())
    return convert(invoice.total, rate, common.base_currency())


def approval_needed(invoice) -> bool:
    policy = approvals.policy_for_action("invoice.approve")
    return bool(
        policy
        and policy.in_force
        and (policy.amount_threshold is None or _base_amount(invoice) >= policy.amount_threshold)
    )


@transaction.atomic
def approve_invoice(request, pk):
    """Approve a draft, or submit it for approval when the invoices policy applies."""
    require(request.user, "invoices.issue")
    lock_company()
    invoice = sync_approval(locked(pk))
    if invoice.status == Invoice.Status.APPROVED:
        return invoice
    if invoice.status != Invoice.Status.DRAFT:
        raise BusinessRuleViolation("Only draft invoices can be approved.")
    if invoice.total <= 0 or not invoice.lines.exists():
        raise ValidationError({"lines": "An invoice needs lines with a positive total."})
    if approval_needed(invoice):
        invoice.approval = approvals.submit(
            request,
            action="invoice.approve",
            subject_key=f"invoice:{invoice.pk}",
            title=(
                f"Approve invoice for {invoice.customer.name} — {invoice.currency} {invoice.total}"
            )[:200],
            payload=strings(
                {"invoice_id": invoice.pk, "revision": invoice.revision, "total": invoice.total}
            ),
        )
        invoice.status = Invoice.Status.PENDING_APPROVAL
    else:
        invoice.status = Invoice.Status.APPROVED
        invoice.approved_by, invoice.approved_at = request.user, timezone.now()
    invoice.save()
    record(
        "billing.invoice_approval",
        request=request,
        target=invoice,
        after={"status": invoice.status},
    )
    return invoice


def execute_approval(request, approval, approver):
    invoice = locked(approval.payload["invoice_id"])
    if (
        invoice.status != Invoice.Status.PENDING_APPROVAL
        or invoice.revision != approval.payload["revision"]
    ):
        raise BusinessRuleViolation("The invoice changed after it was submitted for approval.")
    invoice.status = Invoice.Status.APPROVED
    invoice.approved_by, invoice.approved_at = approver, timezone.now()
    invoice.save()
    return f"invoice:{invoice.pk}"


def _snapshot(invoice, result, *, rate, base_total, base):
    customer = invoice.customer
    milestone = invoice.milestone
    return strings(
        {
            "number": invoice.number,
            "issue_date": invoice.issue_date,
            "due_date": invoice.due_date,
            "currency": invoice.currency,
            "reference": invoice.reference,
            "notes": invoice.notes,
            "prices_include_tax": invoice.prices_include_tax,
            "customer": {
                k: getattr(customer, k)
                for k in (
                    "code",
                    "name",
                    "contact_name",
                    "email",
                    "phone",
                    "tax_id",
                    "address",
                    "city",
                    "country",
                )
            },
            "company": common.company_identity(),
            "project": {"reference": invoice.project.reference, "name": invoice.project.name}
            if invoice.project
            else None,
            "milestone": {"name": milestone.name, "percent": milestone.percent}
            if milestone
            else None,
            "sales_order": invoice.sales_order.number if invoice.sales_order else None,
            "lines": [
                {
                    "position": line.position,
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "discount_type": line.discount_type,
                    "discount_value": line.discount_value,
                    "subtotal": line.subtotal,
                    "line_discount": line.line_discount,
                    "amount": line.subtotal - line.line_discount,
                    "document_discount": line.document_discount,
                    "taxable": line.taxable,
                    "tax": line.tax,
                    "total": line.total,
                    "tax_rate": line.tax_rate,
                    "tax_code": line.tax_code.code if line.tax_code else None,
                }
                for line in invoice.lines.select_related("tax_code")
            ],
            "taxes": [
                {k: t[k] for k in ("code", "rate", "taxable", "tax")} for t in result["taxes"]
            ],
            "totals": {
                k: result[k]
                for k in (
                    "subtotal",
                    "line_discount",
                    "document_discount",
                    "taxable",
                    "tax",
                    "total",
                )
            },
            "format": common.money_format(invoice.currency),
            **common.tax_labels(),
            "exchange_rate": rate,
            "base_currency": base,
            "base_total": base_total,
        }
    )


def _journal_lines(invoice, rate, source, base_total, receivable):
    """Dr receivable / Cr revenue per account / Cr output tax per revision, exact in base."""
    credits = {}
    for line in invoice.lines.select_related("tax_revision"):
        if line.taxable:
            key = ("revenue", line.revenue_account_id, None)
            credits[key] = credits.get(key, ZERO) + line.taxable
        if line.tax:
            rev = line.tax_revision
            key = ("tax", rev.output_account_id, rev.pk)
            credits[key] = credits.get(key, ZERO) + line.tax
    keys = list(credits)
    bases = calculation.allocate(base_total, [credits[k] for k in keys], common.base_currency())
    fx = {"exchange_rate": str(rate), "rate_source": source}
    lines = [
        {
            "account_id": receivable.pk,
            "currency": invoice.currency,
            "debit": str(invoice.total),
            "base_debit": str(base_total),
            "description": f"Receivable — {invoice.customer.name}",
            "dimensions": {"customer": invoice.customer_id, "invoice": invoice.pk},
            **fx,
        }
    ]
    for (kind, account_id, revision_id), base in zip(keys, bases, strict=True):
        lines.append(
            {
                "account_id": account_id,
                "currency": invoice.currency,
                "credit": str(credits[(kind, account_id, revision_id)]),
                "base_credit": str(base),
                "description": "Output tax" if kind == "tax" else "Revenue",
                "valuation": "allocated",
                "tax_revision_id": revision_id,
                **fx,
            }
        )
    return lines


@transaction.atomic
def issue_invoice(request, pk):
    """Issue an approved invoice: number, snapshot, branding version and receivable journal."""
    authority = authorize(request.user, "invoice", "issue")
    company = lock_company()
    invoice = sync_approval(locked(pk))
    if invoice.number:
        return invoice
    if invoice.status == Invoice.Status.DRAFT:
        if approval_needed(invoice):
            raise BusinessRuleViolation(
                "This invoice needs approval before it can be issued. Submit it for approval.",
                code="approval_required",
            )
        approve_invoice(request, pk)
        invoice.refresh_from_db()
    if invoice.status == Invoice.Status.PENDING_APPROVAL:
        raise BusinessRuleViolation(
            "This invoice is waiting for approval.", code="approval_pending"
        )
    if invoice.status != Invoice.Status.APPROVED:
        raise BusinessRuleViolation("Only approved invoices can be issued.")
    if not invoice.customer.is_active:
        raise BusinessRuleViolation("The customer is inactive.")
    branding = common.published_branding()
    receivable = common.control("receivable")
    # Recompute with the rates effective on the invoice date; never issue stale totals.
    rows = [
        {
            "quantity": str(line.quantity),
            "unit_price": str(line.unit_price),
            "discount_type": line.discount_type,
            "discount_value": str(line.discount_value),
            "tax_code_id": line.tax_code_id,
        }
        for line in invoice.lines.all()
    ]
    result = _calculate(invoice, rows)
    if result["total"] != invoice.total or any(
        r["tax"] != line.tax for r, line in zip(result["lines"], invoice.lines.all(), strict=True)
    ):
        raise BusinessRuleViolation(
            "Tax rates changed since this draft was saved. Save the draft again and re-approve.",
            code="stale_totals",
        )
    if invoice.total <= 0:
        raise ValidationError({"lines": "An invoice total must be positive."})
    for line in invoice.lines.select_related("revenue_account", "sales_order_line"):
        account = line.revenue_account
        if not account.is_active or not account.is_postable:
            raise BusinessRuleViolation(f"Revenue account {account.code} is no longer postable.")
    if invoice.sales_order_id:
        order = SalesOrder.objects.select_for_update().get(pk=invoice.sales_order_id)
        done = order_invoiced_quantities(order)
        for line in invoice.lines.exclude(sales_order_line=None).select_related("sales_order_line"):
            ordered = line.sales_order_line.quantity
            if done.get(line.sales_order_line_id, ZERO) + line.quantity > ordered:
                raise BusinessRuleViolation(
                    f"Line {line.position} would invoice more than the ordered quantity.",
                    code="order_overinvoiced",
                )
    base = company.base_currency
    rate, source = rate_for(invoice.currency, invoice.issue_date, base)
    base_total = convert(invoice.total, rate, base)
    number = next_number(
        "invoice", invoice.issue_date, lambda n: Invoice.objects.filter(number=n).exists()
    )
    journal = posting.post_journal(
        actor=request.user,
        authority=authority,
        request_context=request,
        posting_key=common.posting_key("invoice", invoice.pk, "issue"),
        source_type="invoice",
        source_id=invoice.pk,
        source_action="issue",
        posting_date=invoice.issue_date,
        description=f"Invoice {number} — {invoice.customer.name}"[:500],
        lines=_journal_lines(invoice, rate, source, base_total, receivable),
    )
    invoice.number = number
    invoice.status = Invoice.Status.ISSUED
    invoice.issued_by, invoice.issued_at = request.user, timezone.now()
    invoice.journal = journal
    invoice.branding_version = branding
    invoice.exchange_rate, invoice.base_total = rate, base_total
    invoice.snapshot = _snapshot(invoice, result, rate=rate, base_total=base_total, base=base)
    invoice.pdf_status = "pending"
    invoice.save()
    if invoice.sales_order_id:
        refresh_order_status(SalesOrder.objects.get(pk=invoice.sales_order_id))
    record(
        "billing.invoice_issued",
        request=request,
        target=invoice,
        after={"number": number, "total": invoice.total, "journal": journal.number},
    )
    return invoice


def issue_and_render(request, pk):
    """Issue (one transaction), then render the official PDF after commit."""
    from apps.documents.services import generate_pdf

    invoice = issue_invoice(request, pk)
    if invoice.pdf_status != "ready":
        generate_pdf("invoice", invoice.pk)
        invoice.refresh_from_db()
    return invoice


def settle_status(invoice: Invoice) -> None:
    if invoice.status == Invoice.Status.VOID:
        return
    if invoice.outstanding > 0:
        paid = invoice.amount_paid > 0 or invoice.amount_credited > 0
        invoice.status = Invoice.Status.PARTIALLY_PAID if paid else Invoice.Status.ISSUED
    else:
        invoice.status = Invoice.Status.PAID if invoice.amount_paid > 0 else Invoice.Status.CREDITED


def reserved(invoice: Invoice, *, exclude_payment=None) -> Decimal:
    """Amount held by payments that are recorded but not yet verified."""
    qs = PaymentAllocation.objects.filter(
        invoice=invoice, payment__status__in=("pending_verification", "awaiting_approval")
    )
    if exclude_payment is not None:
        qs = qs.exclude(payment=exclude_payment)
    return sum((a.amount for a in qs), ZERO)


@transaction.atomic
def void_invoice(request, pk, reason, on=None):
    authority = authorize(request.user, "invoice", "void")
    lock_company()
    invoice = locked(pk)
    if not reason.strip():
        raise ValidationError({"reason": "Explain why the invoice is voided."})
    if invoice.status == Invoice.Status.VOID:
        return invoice
    if invoice.status not in Invoice.ISSUED_STATES:
        raise BusinessRuleViolation("Only issued invoices can be voided; cancel drafts instead.")
    if invoice.amount_paid or invoice.amount_credited or reserved(invoice):
        raise BusinessRuleViolation(
            "Invoices with payments, pending payments or credits cannot be voided. Issue a credit "
            "note instead.",
            code="invoice_settled",
        )
    reversal = posting.reverse(
        request,
        invoice.journal_id,
        on or timezone.localdate(),
        reason.strip()[:500],
        common.posting_key("invoice", invoice.pk, "void"),
        authority=authority,
    )
    invoice.status = Invoice.Status.VOID
    invoice.void_journal = reversal
    invoice.voided_by, invoice.voided_at = request.user, timezone.now()
    invoice.void_reason = reason.strip()[:500]
    invoice.save()
    if invoice.sales_order_id:
        refresh_order_status(SalesOrder.objects.select_for_update().get(pk=invoice.sales_order_id))
    record("billing.invoice_voided", request=request, target=invoice, reason=invoice.void_reason)
    return invoice
