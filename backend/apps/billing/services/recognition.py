"""Source-owned point-in-time recognition for explicitly configured stock contracts.

Dispatch moves company-owned stock to transit. Only documented control transfer
recognizes COGS and, for control-based contracts, revenue. Invoice timing alone
does not choose the recognition trigger. No existing invoice is restated.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from rest_framework.exceptions import ValidationError

from apps.accounting.money import ZERO, convert, decimal, strings
from apps.accounting.services.adapters import authorize
from apps.accounting.services.posting import balance_with_fx, post_journal
from apps.accounting.services.setup import lock_company, rate_for
from apps.accounts.authorization import require
from apps.audit.services import record
from apps.catalog.models import ItemProfile
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory import services as stock
from apps.sales import calculation
from apps.sales.models import SalesOrderLine
from apps.sales.services import _get

from ..fulfillment_models import (
    ControlTransfer,
    CustomerReturn,
    DeferredCreditAllocation,
    Dispatch,
    DispatchRecall,
    FulfillmentPolicy,
    InvoiceRecognitionBinding,
)
from ..models import Invoice
from . import common


def _active_bindings(policy, include_invoice=None):
    active = Q(invoice_line__invoice__status__in=Invoice.ISSUED_STATES)
    if include_invoice:
        active |= Q(invoice_line__invoice_id=include_invoice)
    return policy.bindings.filter(active).select_related("invoice_line__invoice").order_by("pk")


def _portion(total, qty, remaining_qty, currency):
    if qty < 0 or qty > remaining_qty or remaining_qty <= 0:
        raise BusinessRuleViolation("The quantity exceeds the remaining source allocation.")
    if qty == remaining_qty:
        return total
    return calculation.allocate(total, [qty, remaining_qty - qty], currency)[0]


def _contract_room(policy, include_invoice=None):
    bound = list(_active_bindings(policy, include_invoice))
    transfers = list(policy.transfers.all())
    qty = decimal(policy.snapshot["quantity"]) - sum((b.deferred_quantity for b in bound), ZERO)
    qty -= sum((t.unbilled_quantity for t in transfers), ZERO)
    value = policy.net_contract - sum((b.deferred_native for b in bound), ZERO)
    value -= sum((t.unbilled_native for t in transfers), ZERO)
    return qty, value


def _net_dispatched(policy):
    sent = policy.dispatches.aggregate(q=Sum("quantity"))["q"] or ZERO
    recalled = (
        DispatchRecall.objects.filter(dispatch__policy=policy).aggregate(q=Sum("quantity"))["q"]
        or ZERO
    )
    return sent - recalled


def _deferred_remaining(binding):
    qty, native, base = binding.deferred_quantity, binding.deferred_native, binding.deferred_base
    for event in binding.policy.transfers.all():
        for portion in event.deferred_snapshot:
            if portion["binding_id"] == binding.pk:
                qty -= Decimal(portion["quantity"])
                native -= Decimal(portion["native"])
                base -= Decimal(portion["base"])
    credits = binding.credits.filter(credit_line__credit_note__status="issued").aggregate(
        native=Sum("native"), base=Sum("base")
    )
    return qty, native - (credits["native"] or ZERO), base - (credits["base"] or ZERO)


def _unbilled_remaining(event, include_invoice=None):
    qty, native, base = event.unbilled_quantity, event.unbilled_native, event.unbilled_base
    for binding in _active_bindings(event.policy, include_invoice):
        for portion in binding.unbilled_snapshot:
            if portion["transfer_id"] == str(event.pk):
                qty -= Decimal(portion["quantity"])
                native -= Decimal(portion["native"])
                base -= Decimal(portion["base"])
    return qty, native, base


@transaction.atomic
def configure(request, data):
    require(request.user, "fulfillment.manage", "invoices.issue", "finance.view")
    lock_company()
    line = _get(SalesOrderLine, data["order_line_id"])
    order = line.order
    if order.status not in ("confirmed", "partially_invoiced", "invoiced") or not line.item_id:
        raise BusinessRuleViolation("Configure a confirmed catalog order line.")
    profile = ItemProfile.objects.filter(item=line.item).first()
    if not profile or profile.kind != "stock":
        raise ValidationError(
            {
                "order_line_id": "This workflow covers tracked products. "
                "Existing service invoicing remains available."
            }
        )
    if FulfillmentPolicy.objects.filter(order_line=line).exists():
        raise BusinessRuleViolation("The documented recognition policy is immutable.")
    already_invoiced = line.invoice_lines.filter(invoice__status__in=Invoice.ISSUED_STATES).exists()
    if already_invoiced and data["trigger"] != "invoice":
        raise BusinessRuleViolation(
            "Issued legacy revenue cannot be silently reclassified. Preserve invoice "
            "treatment and use reviewed corrections."
        )
    if data["trigger"] == "invoice":
        invoiced_qty = (
            line.invoice_lines.filter(invoice__status__in=Invoice.ISSUED_STATES).aggregate(
                q=Sum("quantity")
            )["q"]
            or ZERO
        )
        if not already_invoiced or invoiced_qty != line.quantity:
            raise BusinessRuleViolation(
                "New tracked contracts use control transfer. Legacy invoice treatment "
                "is retained only for already fully invoiced lines."
            )
    result = calculation.calculate(
        currency=order.currency,
        on=order.order_date,
        prices_include_tax=order.prices_include_tax,
        lines=[
            {
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "discount_type": line.discount_type,
                "discount_value": str(line.discount_value),
                "tax_code_id": line.tax_code_id,
            }
        ],
    )
    obj = FulfillmentPolicy.objects.create(
        order_line=line,
        trigger=data["trigger"],
        contract_reference=data["contract_reference"],
        reason=data["reason"],
        net_contract=result["taxable"],
        revenue_account=common.posting_account(line.item.revenue_account_id, kind="revenue"),
        snapshot=strings(
            {
                "quantity": line.quantity,
                "currency": order.currency,
                "item_id": line.item_id,
                "item_code": line.item.code,
                "unit": line.item.unit,
                "customer_id": order.customer_id,
                "project_id": order.project_id,
            }
        ),
        created_by=request.user,
    )
    record("fulfillment.policy_documented", request=request, target=obj, after=data)
    return obj


@transaction.atomic
def dispatch(request, data):
    require(request.user, "fulfillment.manage", "inventory.manage", "finance.view")
    lock_company()
    digest = stock.fingerprint(data)
    previous = Dispatch.objects.filter(key=data["key"]).first()
    if previous:
        if previous.fingerprint != digest:
            raise BusinessRuleViolation("The dispatch key conflicts with existing content.")
        return previous
    policy = _get(FulfillmentPolicy, data["policy_id"])
    if policy.order_line.order.status == "cancelled":
        raise BusinessRuleViolation("The sales order is cancelled.")
    qty = decimal(data["quantity"], "quantity")
    sent = _net_dispatched(policy)
    direct = (
        policy.transfers.filter(dispatch__isnull=True).aggregate(q=Sum("quantity"))["q"] or ZERO
    )
    if qty <= 0 or sent + direct + qty > decimal(policy.snapshot["quantity"]):
        raise BusinessRuleViolation("Dispatch exceeds the confirmed contract quantity.")
    movement = stock.transfer(
        request,
        {
            "item_id": policy.snapshot["item_id"],
            "from_location_id": data["from_location_id"],
            "to_location_id": data["transit_location_id"],
            "date": data["date"],
            "quantity": str(qty),
            "reason": data["evidence"][:500],
            "key": data["key"],
        },
    )
    obj = Dispatch.objects.create(
        policy=policy,
        date=data["date"],
        quantity=qty,
        from_location_id=data["from_location_id"],
        transit_location_id=data["transit_location_id"],
        reference=data["reference"],
        evidence=data["evidence"],
        movement=movement,
        key=data["key"],
        fingerprint=digest,
        created_by=request.user,
    )
    record(
        "fulfillment.dispatched",
        request=request,
        target=obj,
        after={"quantity": qty, "accounting_effect": "none; company-owned stock in transit"},
    )
    return obj


@transaction.atomic
def transfer_control(request, data):
    require(request.user, "fulfillment.manage", "inventory.post", "invoices.issue", "finance.view")
    company = lock_company()
    digest = stock.fingerprint(data)
    previous = ControlTransfer.objects.filter(key=data["key"]).first()
    if previous:
        if previous.fingerprint != digest:
            raise BusinessRuleViolation("The control-transfer key conflicts with existing content.")
        return previous
    policy = _get(FulfillmentPolicy, data["policy_id"])
    if policy.order_line.order.status == "cancelled":
        raise BusinessRuleViolation("The sales order is cancelled.")
    qty = decimal(data["quantity"], "quantity")
    fulfilled = policy.transfers.aggregate(q=Sum("quantity"))["q"] or ZERO
    if qty <= 0 or fulfilled + qty > decimal(policy.snapshot["quantity"]):
        raise BusinessRuleViolation("Control transfer exceeds the confirmed contract quantity.")
    sent = _get(Dispatch, data["dispatch_id"]) if data.get("dispatch_id") else None
    location_id = data["location_id"]
    if sent:
        used = sent.transfers.aggregate(q=Sum("quantity"))["q"] or ZERO
        used += sent.recalls.aggregate(q=Sum("quantity"))["q"] or ZERO
        if (
            sent.policy_id != policy.pk
            or sent.transit_location_id != location_id
            or used + qty > sent.quantity
        ):
            raise BusinessRuleViolation(
                "Control quantity/location does not match remaining dispatched goods."
            )
    else:
        sent_qty = _net_dispatched(policy)
        direct_qty = (
            policy.transfers.filter(dispatch__isnull=True).aggregate(q=Sum("quantity"))["q"] or ZERO
        )
        if sent_qty + direct_qty + qty > decimal(policy.snapshot["quantity"]):
            raise BusinessRuleViolation(
                "Dispatched goods reserve this contract. "
                "Select their dispatch or recall them first."
            )
    item_id = policy.snapshot["item_id"]
    profile = stock._validate(item_id, location_id, data["date"], qty)
    stock.enabled()
    if stock.position(item_id, location_id)["quantity"] < qty:
        raise BusinessRuleViolation("The fulfillment location has insufficient stock.")
    cogs = common.posting_account(profile.cogs_account_id, kind="expense")
    if cogs.account_type != "expense":
        raise ValidationError({"item_id": "Configure an expense cost-of-sales account."})
    cost = stock.issue_cost(item_id, qty, company.base_currency)
    currency = policy.snapshot["currency"]
    fx, rate_source = rate_for(currency, data["date"], company.base_currency)
    raw, allocations, remaining = [], [], qty
    net, base_revenue, unbilled_native, unbilled_base, unbilled_qty = ZERO, ZERO, ZERO, ZERO, ZERO
    if cost:
        raw.extend(
            [
                {
                    "account_id": cogs.pk,
                    "currency": company.base_currency,
                    "debit": str(cost),
                    "dimensions": {
                        "project": policy.snapshot["project_id"],
                        "order_line": policy.order_line_id,
                    },
                },
                {
                    "account_id": stock.control("inventory").pk,
                    "currency": company.base_currency,
                    "credit": str(cost),
                },
            ]
        )
    if policy.trigger == "control_transfer":
        for binding in _active_bindings(policy):
            available, native, base = _deferred_remaining(binding)
            if available <= 0 or remaining <= 0:
                continue
            if binding.invoice_line.invoice.issue_date > data["date"]:
                raise BusinessRuleViolation(
                    "A later-dated invoice already exists. Use a reviewed chronological "
                    "correction; historical journals cannot be rewritten."
                )
            take = min(remaining, available)
            n = _portion(native, take, available, currency)
            b = _portion(base, take, available, company.base_currency)
            allocations.append(
                strings({"binding_id": binding.pk, "quantity": take, "native": n, "base": b})
            )
            remaining -= take
            net += n
            base_revenue += b
            if n:
                raw.append(
                    {
                        "account_id": stock.control("deferred_revenue").pk,
                        "currency": currency,
                        "debit": str(n),
                        "base_debit": str(b),
                        "exchange_rate": str(fx),
                        "rate_source": "Historical invoiced consideration",
                        "valuation": "historical",
                    }
                )
        if remaining:
            room_qty, room_value = _contract_room(policy)
            unbilled_qty = remaining
            unbilled_native = _portion(room_value, remaining, room_qty, currency)
            unbilled_base = convert(unbilled_native, fx, company.base_currency)
            net += unbilled_native
            base_revenue += unbilled_base
            if unbilled_native:
                raw.append(
                    {
                        "account_id": stock.control("unbilled_revenue").pk,
                        "currency": currency,
                        "debit": str(unbilled_native),
                        "base_debit": str(unbilled_base),
                        "exchange_rate": str(fx),
                        "rate_source": rate_source,
                    }
                )
        if net:
            raw.append(
                {
                    "account_id": policy.revenue_account_id,
                    "currency": currency,
                    "credit": str(net),
                    "base_credit": str(base_revenue),
                    "exchange_rate": str(fx),
                    "rate_source": "Documented control-transfer consideration",
                    "valuation": "allocated",
                    "dimensions": {
                        "project": policy.snapshot["project_id"],
                        "order_line": policy.order_line_id,
                    },
                }
            )
    obj = ControlTransfer(
        policy=policy,
        dispatch=sent,
        location_id=location_id,
        date=data["date"],
        quantity=qty,
        reference=data["reference"],
        evidence=data["evidence"],
        currency=currency,
        net_native=net,
        base_revenue=base_revenue,
        base_cogs=cost,
        cogs_account=cogs,
        unbilled_quantity=unbilled_qty,
        unbilled_native=unbilled_native,
        unbilled_base=unbilled_base,
        deferred_snapshot=allocations,
        key=data["key"],
        fingerprint=digest,
        created_by=request.user,
    )
    authority = authorize(request.user, "fulfillment_control", "post")
    journal = (
        post_journal(
            actor=request.user,
            authority=authority,
            request_context=request,
            source_type="fulfillment_control",
            source_id=obj.pk,
            source_action="post",
            posting_key=data["key"],
            posting_date=obj.date,
            description=f"Control transferred: {obj.reference}",
            lines=raw,
        )
        if raw
        else None
    )
    obj.journal = journal
    obj.movement = stock._persist(
        request,
        item_id=item_id,
        location_id=location_id,
        on=obj.date,
        kind="issue",
        qty=-qty,
        value=-cost,
        key=f"control:{obj.pk}",
        source_type="fulfillment_control",
        source_id=str(obj.pk),
        reason=obj.evidence[:500],
        digest=digest,
        journal=journal,
    )
    obj.full_clean()
    obj.save()
    record(
        "fulfillment.control_transferred",
        request=request,
        target=obj,
        after={
            "quantity": qty,
            "revenue": net,
            "base_revenue": base_revenue,
            "cogs": cost,
            "trigger": policy.trigger,
            "reference": obj.reference,
        },
    )
    return obj


def invoice_lines(request, invoice, rate, source, base_total, receivable):
    """Return replacement lines only for explicitly control-based contracts."""
    all_policies = (
        {
            p.order_line_id: p
            for p in FulfillmentPolicy.objects.filter(order_line__order_id=invoice.sales_order_id)
        }
        if invoice.sales_order_id
        else {}
    )
    for line in invoice.lines.select_related("item", "sales_order_line"):
        tracked = ItemProfile.objects.filter(item_id=line.item_id, kind="stock").exists()
        if tracked and line.sales_order_line_id not in all_policies:
            raise BusinessRuleViolation(
                "Tracked products require a confirmed sales order and documented "
                "fulfillment policy before new invoicing."
            )
        policy = all_policies.get(line.sales_order_line_id)
        if policy and (
            line.item_id != policy.snapshot["item_id"]
            or invoice.customer_id != policy.snapshot["customer_id"]
            or invoice.currency != policy.snapshot["currency"]
        ):
            raise BusinessRuleViolation(
                "Invoice identity differs from the frozen fulfillment contract."
            )
    policies = {pk: p for pk, p in all_policies.items() if p.trigger == "control_transfer"}
    if not policies:
        return None
    require(request.user, "invoices.issue", "fulfillment.manage", "finance.view")
    base = common.base_currency()
    parts = []
    for line in invoice.lines.select_related("tax_revision"):
        if line.taxable:
            parts.append((line, "net", line.taxable))
        if line.tax:
            parts.append((line, "tax", line.tax))
    bases = calculation.allocate(base_total, [p[2] for p in parts], base)
    raw = [
        {
            "account_id": receivable.pk,
            "currency": invoice.currency,
            "debit": str(invoice.total),
            "base_debit": str(base_total),
            "exchange_rate": str(rate),
            "rate_source": source,
            "dimensions": {"customer": invoice.customer_id, "invoice": invoice.pk},
        }
    ]
    for (line, kind, value), line_base in zip(parts, bases, strict=True):
        policy = policies.get(line.sales_order_line_id)
        if kind == "tax" or not policy:
            raw.append(
                {
                    "account_id": line.tax_revision.output_account_id
                    if kind == "tax"
                    else line.revenue_account_id,
                    "currency": invoice.currency,
                    "credit": str(value),
                    "base_credit": str(line_base),
                    "exchange_rate": str(rate),
                    "rate_source": source,
                    "valuation": "allocated",
                    "tax_revision_id": line.tax_revision_id if kind == "tax" else None,
                }
            )
            continue
        remaining, allocations, cleared_native, cleared_base = line.quantity, [], ZERO, ZERO
        for event in policy.transfers.order_by("date", "created_at", "pk"):
            available, native, book = _unbilled_remaining(event, invoice.pk)
            if available <= 0 or remaining <= 0:
                continue
            if event.date > invoice.issue_date:
                raise BusinessRuleViolation(
                    "A later control-transfer posting exists. "
                    "Use a reviewed chronological correction."
                )
            take = min(available, remaining)
            n, b = (
                _portion(native, take, available, invoice.currency),
                _portion(book, take, available, base),
            )
            allocations.append(
                strings({"transfer_id": str(event.pk), "quantity": take, "native": n, "base": b})
            )
            remaining -= take
            cleared_native += n
            cleared_base += b
        deferred_native = value - cleared_native
        room_qty, room_value = _contract_room(policy, invoice.pk)
        expected = (
            _portion(room_value, remaining, room_qty, invoice.currency) if remaining else ZERO
        )
        if deferred_native != expected:
            raise BusinessRuleViolation(
                "Invoice net consideration differs from the frozen contract allocation. "
                "Review the contract/rounding explicitly."
            )
        deferred_base = calculation.allocate(line_base, [cleared_native, deferred_native], base)[1]
        InvoiceRecognitionBinding.objects.create(
            invoice_line=line,
            policy=policy,
            unbilled_quantity=line.quantity - remaining,
            unbilled_native=cleared_native,
            unbilled_base=cleared_base,
            deferred_quantity=remaining,
            deferred_native=deferred_native,
            deferred_base=deferred_base,
            unbilled_snapshot=allocations,
        )
        for purpose, native, book in (
            ("unbilled_revenue", cleared_native, cleared_base),
            ("deferred_revenue", deferred_native, deferred_base),
        ):
            if native:
                raw.append(
                    {
                        "account_id": stock.control(purpose).pk,
                        "currency": invoice.currency,
                        "credit": str(native),
                        "base_credit": str(book),
                        "exchange_rate": str(rate),
                        "rate_source": "Historical recognized amount"
                        if purpose == "unbilled_revenue"
                        else source,
                        "valuation": "historical" if purpose == "unbilled_revenue" else "allocated",
                    }
                )
    raw, _, _, _ = balance_with_fx(raw, lock_company(), invoice.issue_date)
    return raw


def credit_debits(note, parts, base_total, rate, base):
    """Credits reduce unperformed invoiced consideration before recognized revenue."""
    ids = [line.pk for _, line, _, _ in parts]
    bindings = {
        b.invoice_line_id: b
        for b in InvoiceRecognitionBinding.objects.filter(invoice_line_id__in=ids).select_related(
            "policy"
        )
    }
    if not bindings:
        return None
    weights, rows = [], []
    for cl, line, taxable, tax in parts:
        if taxable:
            rows.append((cl, line, "net", taxable))
            weights.append(taxable)
        if tax:
            rows.append((cl, line, "tax", tax))
            weights.append(tax)
    bases = calculation.allocate(base_total, weights, base)
    raw = []
    for (cl, line, kind, value), book in zip(rows, bases, strict=True):
        binding = bindings.get(line.pk)
        if kind == "tax" or binding is None:
            raw.append(
                {
                    "account_id": line.tax_revision.output_account_id
                    if kind == "tax"
                    else line.revenue_account_id,
                    "currency": note.invoice.currency,
                    "debit": str(value),
                    "base_debit": str(book),
                    "exchange_rate": str(rate),
                    "rate_source": "Historical invoice rate",
                    "valuation": "allocated",
                    "tax_revision_id": line.tax_revision_id if kind == "tax" else None,
                }
            )
            continue
        _, pending_native, pending_base = _deferred_remaining(binding)
        deferred = min(value, pending_native)
        deferred_base = _portion(pending_base, deferred, pending_native, base) if deferred else ZERO
        if deferred:
            DeferredCreditAllocation.objects.create(
                credit_line=cl, binding=binding, native=deferred, base=deferred_base
            )
        revenue_native = value - deferred
        revenue_base = calculation.allocate(book, [deferred, revenue_native], base)[1]
        for account, native, converted in (
            (stock.control("deferred_revenue").pk if deferred else None, deferred, deferred_base),
            (binding.policy.revenue_account_id, revenue_native, revenue_base),
        ):
            if native:
                raw.append(
                    {
                        "account_id": account,
                        "currency": note.invoice.currency,
                        "debit": str(native),
                        "base_debit": str(converted),
                        "exchange_rate": str(rate),
                        "rate_source": "Historical source allocation",
                        "valuation": "historical",
                    }
                )
    return raw


def guard_void(invoice):
    bindings = set(
        InvoiceRecognitionBinding.objects.filter(invoice_line__invoice=invoice).values_list(
            "pk", flat=True
        )
    )
    if not bindings:
        return
    for event in ControlTransfer.objects.filter(policy__bindings__pk__in=bindings).distinct():
        if any(p["binding_id"] in bindings for p in event.deferred_snapshot):
            raise BusinessRuleViolation(
                "Control was transferred against this invoice. Use a traceable "
                "return/credit instead of voiding delivered consideration."
            )


@transaction.atomic
def accept_return(request, data):
    require(request.user, "fulfillment.manage", "inventory.post", "finance.view")
    company = lock_company()
    digest = stock.fingerprint(data)
    previous = CustomerReturn.objects.filter(key=data["key"]).first()
    if previous:
        if previous.fingerprint != digest:
            raise BusinessRuleViolation("The return key conflicts with existing content.")
        return previous
    original = _get(ControlTransfer, data["transfer_id"])
    qty = decimal(data["quantity"], "quantity")
    used = original.returns.aggregate(q=Sum("quantity"), cost=Sum("base_cost"))
    remaining = original.quantity - (used["q"] or ZERO)
    if qty <= 0 or qty > remaining:
        raise BusinessRuleViolation("The return exceeds the original remaining fulfilled quantity.")
    cost = _portion(
        original.base_cogs - (used["cost"] or ZERO), qty, remaining, company.base_currency
    )
    profile = stock._validate(
        original.policy.snapshot["item_id"], data["location_id"], data["date"], qty
    )
    cogs = common.posting_account(original.cogs_account_id, kind="expense")
    authority = authorize(request.user, "customer_return", "receive")
    movement = stock.receive(
        request,
        item_id=profile.item_id,
        location_id=data["location_id"],
        on=data["date"],
        qty=qty,
        value=cost,
        key=f"return:{data['key']}",
        source_type="customer_return",
        source_id=digest,
        authority=authority,
        reason=data["reason"][:500],
        offset=cogs,
        kind="return",
        original=original.movement,
    )
    obj = CustomerReturn.objects.create(
        transfer=original,
        date=data["date"],
        quantity=qty,
        base_cost=cost,
        location_id=data["location_id"],
        movement=movement,
        reason=data["reason"],
        reference=data["reference"],
        key=data["key"],
        fingerprint=digest,
        created_by=request.user,
    )
    record(
        "fulfillment.return_accepted",
        request=request,
        target=obj,
        after={
            "quantity": qty,
            "original_cost": cost,
            "revenue_effect": "none; credit notes are separate",
        },
    )
    return obj


@transaction.atomic
def recall_dispatch(request, dispatch_id, data):
    require(request.user, "fulfillment.manage", "inventory.manage", "finance.view")
    lock_company()
    digest = stock.fingerprint({**data, "dispatch_id": str(dispatch_id)})
    previous = DispatchRecall.objects.filter(key=data["key"]).first()
    if previous:
        if previous.fingerprint != digest:
            raise BusinessRuleViolation("The recall key conflicts with existing content.")
        return previous
    sent = _get(Dispatch, dispatch_id)
    controlled = sent.transfers.aggregate(q=Sum("quantity"))["q"] or ZERO
    recalled = sent.recalls.aggregate(q=Sum("quantity"))["q"] or ZERO
    qty = decimal(data["quantity"], "quantity")
    if qty <= 0 or controlled + recalled + qty > sent.quantity:
        raise BusinessRuleViolation(
            "Only dispatched goods still owned by the company can be recalled."
        )
    movement = stock.transfer(
        request,
        {
            "item_id": sent.policy.snapshot["item_id"],
            "from_location_id": sent.transit_location_id,
            "to_location_id": data["location_id"],
            "date": data["date"],
            "quantity": str(qty),
            "reason": data["reason"][:500],
            "key": f"recall:{data['key']}",
        },
    )
    obj = DispatchRecall.objects.create(
        dispatch=sent,
        date=data["date"],
        quantity=qty,
        location_id=data["location_id"],
        movement=movement,
        reason=data["reason"],
        key=data["key"],
        fingerprint=digest,
        created_by=request.user,
    )
    record("fulfillment.dispatch_recalled", request=request, target=obj, after={"quantity": qty})
    return obj
