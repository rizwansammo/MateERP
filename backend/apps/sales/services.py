"""Customer, project, billing-item and sales-order rules. Orders never create receivables."""

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounting.models import Account, TaxCode
from apps.accounting.money import ZERO, decimal, money
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import require
from apps.audit.services import record
from apps.company.models import DocumentSequence
from apps.company.services import get_business_settings, next_number
from apps.core.exceptions import BusinessRuleViolation

from . import calculation
from .models import (
    BillingItem,
    Customer,
    CustomerContact,
    Milestone,
    Project,
    SalesOrder,
    SalesOrderLine,
)

CUSTOMER_FIELDS = (
    "name",
    "contact_name",
    "email",
    "phone",
    "tax_id",
    "address",
    "city",
    "country",
    "currency",
    "payment_terms_days",
    "notes",
    "is_active",
)


def enabled_currency(currency, field="currency"):
    if currency not in get_business_settings().enabled_currencies:
        raise ValidationError({field: f"{currency} is not an enabled currency."})
    return currency


def next_code(key, prefix, model, field="code"):
    """Sequential master-data codes such as CUS-00001; skips codes already taken."""
    DocumentSequence.objects.get_or_create(key=key, scope="all")
    seq = DocumentSequence.objects.select_for_update().get(key=key, scope="all")
    while True:
        seq.last_value += 1
        code = f"{prefix}-{seq.last_value:05d}"
        if not model.objects.filter(**{field: code}).exists():
            break
    seq.save(update_fields=["last_value"])
    return code


def _get(model, pk, *, lock=True):
    qs = model.objects.select_for_update() if lock else model.objects
    obj = qs.filter(pk=pk).first()
    if obj is None:
        raise NotFound()
    return obj


def _assign(obj, data, fields):
    before = {f: getattr(obj, f) for f in fields if obj.pk}
    for f in fields:
        if f in data:
            setattr(obj, f, data[f])
    return before


@transaction.atomic
def save_customer(request, data, pk=None):
    require(request.user, "sales.manage")
    lock_company()
    obj = _get(Customer, pk) if pk else Customer(created_by=request.user)
    if pk and "currency" in data and data["currency"] != obj.currency and has_documents(obj):
        raise BusinessRuleViolation(
            "The customer currency is locked by issued documents.", code="currency_locked"
        )
    before = _assign(obj, data, CUSTOMER_FIELDS)
    if not obj.name.strip():
        raise ValidationError({"name": "Enter the customer's legal name."})
    enabled_currency(obj.currency)
    if not obj.code:
        obj.code = data.get("code") or next_code("customer", "CUS", Customer)
    obj.full_clean()
    obj.save()
    record(
        "sales.customer_updated" if pk else "sales.customer_created",
        request=request,
        target=obj,
        before=before or None,
        after={f: getattr(obj, f) for f in CUSTOMER_FIELDS},
    )
    return obj


def has_documents(customer):
    if not django_apps.is_installed("apps.billing"):
        return False
    invoice = django_apps.get_model("billing", "Invoice")
    return invoice.objects.filter(customer=customer).exclude(status="draft").exists()


@transaction.atomic
def save_contact(request, customer_pk, data, pk=None):
    require(request.user, "sales.manage")
    customer = _get(Customer, customer_pk)
    obj = _get(CustomerContact, pk) if pk else CustomerContact(customer=customer)
    if obj.customer_id != customer.pk:
        raise NotFound()
    fields = ("name", "role", "email", "phone", "is_primary", "is_active")
    _assign(obj, data, fields)
    if not obj.name.strip():
        raise ValidationError({"name": "Enter the contact's name."})
    if obj.is_primary and obj.is_active:
        customer.contacts.exclude(pk=obj.pk).filter(is_primary=True).update(is_primary=False)
    obj.full_clean()
    obj.save()
    record(
        "sales.contact_updated" if pk else "sales.contact_created",
        request=request,
        target=obj,
        after={"customer": customer.code, **{f: getattr(obj, f) for f in fields}},
    )
    return obj


def invoiced_milestones(project):
    if not django_apps.is_installed("apps.billing"):
        return set()
    invoice = django_apps.get_model("billing", "Invoice")
    return set(
        invoice.objects.filter(milestone__project=project)
        .exclude(status__in=("void", "cancelled"))
        .values_list("milestone_id", flat=True)
    )


@transaction.atomic
def save_project(request, data, pk=None):
    require(request.user, "sales.manage")
    lock_company()
    obj = _get(Project, pk) if pk else Project()
    fields = ("reference", "name", "currency", "contract_value", "status", "notes")
    old_customer = obj.customer_id
    before = _assign(obj, data, fields)
    if "customer_id" in data:
        obj.customer = _get(Customer, data["customer_id"], lock=False)
    if not obj.customer_id:
        raise ValidationError({"customer_id": "Select the project's customer."})
    obj.reference = obj.reference.strip().upper()
    if not obj.reference or not obj.name.strip():
        raise ValidationError({"reference": "Enter a project reference and name."})
    enabled_currency(obj.currency)
    obj.contract_value = money(obj.contract_value, obj.currency, "contract_value")
    locked = invoiced_milestones(obj) if pk else set()
    issued_history = (
        pk
        and django_apps.is_installed("apps.billing")
        and django_apps.get_model("billing", "Invoice")
        .objects.filter(project=obj, number__isnull=False)
        .exists()
    )
    if (locked or issued_history) and (
        before.get("currency") != obj.currency
        or before.get("contract_value") != obj.contract_value
        or old_customer != obj.customer_id
    ):
        raise BusinessRuleViolation(
            "Issued project billing locks the project's customer, currency and contract value."
        )
    obj.full_clean()
    obj.save()
    if "milestones" in data:
        _save_milestones(obj, data["milestones"], locked)
    record(
        "sales.project_updated" if pk else "sales.project_created",
        request=request,
        target=obj,
        after={f: getattr(obj, f) for f in fields},
    )
    return obj


def _save_milestones(project, rows, locked):
    if locked:
        raise BusinessRuleViolation(
            "Milestones cannot change after one has been invoiced.", code="milestone_invoiced"
        )
    if rows and len(rows) > 50:
        raise ValidationError({"milestones": "Use at most 50 milestones."})
    shares = [decimal(r.get("percent"), "milestones.percent", 6) for r in rows]
    if rows and (sum(shares, ZERO) != 100 or any(s <= 0 for s in shares)):
        raise ValidationError(
            {"milestones": "Milestone percentages must be positive and total 100%."}
        )
    amounts = calculation.allocate(project.contract_value, shares, project.currency)
    project.milestones.all().delete()
    for position, (row, share, value) in enumerate(zip(rows, shares, amounts, strict=True), 1):
        if not str(row.get("name", "")).strip():
            raise ValidationError({"milestones": "Name every milestone."})
        Milestone.objects.create(
            project=project, position=position, name=row["name"][:160], percent=share, amount=value
        )


@transaction.atomic
def save_item(request, data, pk=None):
    require(request.user, "sales.manage")
    obj = _get(BillingItem, pk) if pk else BillingItem()
    fields = ("code", "name", "description", "unit", "unit_price", "currency", "is_active")
    _assign(obj, data, fields)
    obj.code = obj.code.strip().upper()
    if not obj.code or not obj.name.strip():
        raise ValidationError({"code": "Enter a code and a name."})
    enabled_currency(obj.currency)
    obj.unit_price = decimal(obj.unit_price, "unit_price", 6)
    if "revenue_account_id" in data:
        account = (
            Account.objects.filter(
                pk=data["revenue_account_id"], account_type="revenue", is_active=True
            ).first()
            if data["revenue_account_id"]
            else None
        )
        if data["revenue_account_id"] and (account is None or not account.is_postable):
            raise ValidationError({"revenue_account_id": "Choose an active revenue account."})
        obj.revenue_account = account
    if "tax_code_id" in data:
        code = (
            TaxCode.objects.filter(pk=data["tax_code_id"]).first() if data["tax_code_id"] else None
        )
        if data["tax_code_id"] and code is None:
            raise ValidationError({"tax_code_id": "Choose a tax code."})
        obj.tax_code = code
    obj.full_clean()
    obj.save()
    record(
        "sales.item_updated" if pk else "sales.item_created",
        request=request,
        target=obj,
        after={f: getattr(obj, f) for f in fields},
    )
    return obj


ORDER_FIELDS = (
    "order_date",
    "currency",
    "title",
    "customer_reference",
    "prices_include_tax",
    "notes",
)


def _order_lines(order, rows):
    """Validate order lines with the shared calculation engine, then store them."""
    payload = []
    for row in rows:
        item = (
            BillingItem.objects.filter(pk=row.get("item_id")).first()
            if row.get("item_id")
            else None
        )
        if row.get("item_id") and (item is None or not item.is_active):
            raise ValidationError({"lines": "Choose an active billing item."})
        payload.append(
            {
                "item": item,
                "description": str(row.get("description") or (item.name if item else "")).strip()[
                    :500
                ],
                "quantity": row.get("quantity", "1"),
                "unit_price": row.get("unit_price", item.unit_price if item else "0"),
                "discount_type": row.get("discount_type", "percent"),
                "discount_value": row.get("discount_value", "0"),
                "tax_code_id": row.get("tax_code_id", item.tax_code_id if item else None),
            }
        )
    if any(not p["description"] for p in payload):
        raise ValidationError({"lines": "Describe every line."})
    result = calculation.calculate(
        currency=order.currency,
        on=order.order_date,
        lines=payload,
        prices_include_tax=order.prices_include_tax,
    )
    order.lines.all().delete()
    for p, calc in zip(payload, result["lines"], strict=True):
        SalesOrderLine.objects.create(
            order=order,
            position=calc["position"],
            item=p["item"],
            description=p["description"],
            quantity=calc["quantity"],
            unit_price=calc["unit_price"],
            discount_type=p["discount_type"],
            discount_value=decimal(p["discount_value"], "discount_value", 6),
            tax_code_id=p["tax_code_id"],
        )
    order.tax, order.total = result["tax"], result["total"]
    order.save(update_fields=["tax", "total"])
    return result


@transaction.atomic
def save_order(request, data, pk=None):
    require(request.user, "sales.manage")
    lock_company()
    order = _get(SalesOrder, pk) if pk else SalesOrder(created_by=request.user)
    if pk:
        if order.status != SalesOrder.Status.DRAFT:
            raise BusinessRuleViolation("Only draft sales orders can be edited.")
        if data.get("revision") != order.revision:
            raise BusinessRuleViolation(
                "This order changed. Reload before saving.", code="stale_revision"
            )
        order.revision += 1
    _assign(order, data, ORDER_FIELDS)
    if "customer_id" in data:
        order.customer = _get(Customer, data["customer_id"], lock=False)
    if not order.customer_id or not order.customer.is_active:
        raise ValidationError({"customer_id": "Select an active customer."})
    if "project_id" in data:
        order.project = (
            _get(Project, data["project_id"], lock=False) if data["project_id"] else None
        )
    if order.project and order.project.customer_id != order.customer_id:
        raise ValidationError({"project_id": "The project belongs to another customer."})
    if not order.order_date:
        raise ValidationError({"order_date": "Enter the order date."})
    order.currency = order.currency or order.customer.currency
    enabled_currency(order.currency)
    if not order.number:
        order.number = next_number(
            "sales_order",
            order.order_date,
            lambda n: SalesOrder.objects.filter(number=n).exists(),
        )
    order.full_clean()
    order.save()
    if "lines" in data or not pk:
        _order_lines(order, data.get("lines", []))
    record(
        "sales.order_updated" if pk else "sales.order_created",
        request=request,
        target=order,
        after={"number": order.number, "revision": order.revision},
    )
    return order


@transaction.atomic
def confirm_order(request, pk):
    require(request.user, "sales.manage")
    lock_company()
    order = _get(SalesOrder, pk)
    if order.status != SalesOrder.Status.DRAFT:
        raise BusinessRuleViolation("Only draft sales orders can be confirmed.")
    if not order.lines.exists():
        raise ValidationError({"lines": "Add at least one line."})
    order.status = SalesOrder.Status.CONFIRMED
    order.confirmed_at = timezone.now()
    order.save()
    record("sales.order_confirmed", request=request, target=order, after={"number": order.number})
    return order


@transaction.atomic
def cancel_order(request, pk, reason):
    require(request.user, "sales.manage")
    lock_company()
    order = _get(SalesOrder, pk)
    if not reason.strip():
        raise ValidationError({"reason": "Explain the cancellation."})
    if order.status not in (SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED):
        raise BusinessRuleViolation("Invoiced or cancelled orders cannot be cancelled.")
    if order_invoiced_quantities(order, include_drafts=True):
        raise BusinessRuleViolation(
            "Delete or cancel the draft invoices created from this order first."
        )
    order.status = SalesOrder.Status.CANCELLED
    order.cancelled_reason = reason.strip()[:500]
    order.save()
    record("sales.order_cancelled", request=request, target=order, reason=order.cancelled_reason)
    return order


def order_invoiced_quantities(order, *, include_drafts=False):
    """Quantities per order line already on invoices (issued, or also drafts)."""
    if not django_apps.is_installed("apps.billing"):
        return {}
    from django.db.models import Sum

    line = django_apps.get_model("billing", "InvoiceLine")
    rows = line.objects.filter(sales_order_line__order=order)
    if include_drafts:
        rows = rows.exclude(invoice__status__in=("void", "cancelled"))
    else:
        rows = rows.filter(invoice__number__isnull=False).exclude(invoice__status="void")
    return {
        r["sales_order_line"]: r["q"]
        for r in rows.values("sales_order_line").annotate(q=Sum("quantity")).order_by()
    }


def refresh_order_status(order):
    """Recompute invoicing progress from issued invoices (called by billing under lock)."""
    if order.status in (SalesOrder.Status.DRAFT, SalesOrder.Status.CANCELLED):
        return order
    done = order_invoiced_quantities(order)
    lines = list(order.lines.all())
    if not any(done.get(x.pk) for x in lines):
        status = SalesOrder.Status.CONFIRMED
    elif all(done.get(x.pk, ZERO) >= x.quantity for x in lines):
        status = SalesOrder.Status.INVOICED
    else:
        status = SalesOrder.Status.PARTIALLY_INVOICED
    if status != order.status:
        order.status = status
        order.save(update_fields=["status"])
    return order
