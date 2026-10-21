"""Read-only report projections. Sources and GL remain owned by their domains."""

from decimal import ROUND_HALF_UP, Decimal, localcontext

from django.db.models import F, Q, Sum
from rest_framework.exceptions import ValidationError

from apps.accounting import reports
from apps.accounting.money import ZERO, quantum, strings
from apps.billing.models import (
    CreditNote,
    CreditNoteLine,
    Invoice,
    InvoiceLine,
    RecurringInvoiceSchedule,
)
from apps.catalog.models import ItemProfile
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory.models import Movement
from apps.purchasing.models import Expense, GoodsReceipt, VendorBill
from apps.sales import calculation

from .aging import aging

LIMIT = 10000


def _bounded(rows):
    values = list(rows[: LIMIT + 1]) if hasattr(rows, "query") else list(rows)
    if len(values) > LIMIT:
        raise BusinessRuleViolation(
            "Narrow the report filters; at most 10,000 grouped records may be requested.",
            code="report_limit",
        )
    return values


def _column(key, label, kind="text"):
    return {"key": key, "label": label, "kind": kind}


def _sum(qs, field):
    return qs.aggregate(v=Sum(field))["v"] or ZERO


def _customer_rows(start, end, filters):
    groups = {}
    for model, date_field, kind in (
        (Invoice, "journal__posting_date", "issued"),
        (Invoice, "void_journal__posting_date", "void"),
        (CreditNote, "journal__posting_date", "credit"),
    ):
        qs = model.objects.filter(**{f"{date_field}__range": (start, end)})
        if filters.get("currency"):
            qs = qs.filter(currency=filters["currency"])
        if filters.get("customer_id"):
            qs = qs.filter(customer_id=filters["customer_id"])
        rows = qs.values("customer_id", "customer__name", "currency").annotate(
            native=Sum("total"), base=Sum("base_total")
        )
        for row in _bounded(rows.order_by("customer_id", "currency")):
            key = (row["customer_id"], row["currency"])
            current = groups.setdefault(
                key,
                {
                    "id": row["customer_id"],
                    "name": row["customer__name"],
                    "currency": row["currency"],
                    "issued": ZERO,
                    "voided": ZERO,
                    "credited": ZERO,
                    "base_net": ZERO,
                    "route": f"/sales/customers/{row['customer_id']}",
                },
            )
            current[
                "issued" if kind == "issued" else "voided" if kind == "void" else "credited"
            ] += row["native"] or ZERO
            current["base_net"] += (row["base"] or ZERO) * (1 if kind == "issued" else -1)
    for row in groups.values():
        row["net"] = row["issued"] - row["voided"] - row["credited"]
    return list(groups.values())


def _product_rows(start, end, filters):
    groups = {}
    for model, prefix, date_field, kind in (
        (InvoiceLine, "invoice", "invoice__journal__posting_date", "issued"),
        (InvoiceLine, "invoice", "invoice__void_journal__posting_date", "void"),
        (CreditNoteLine, "credit_note", "credit_note__journal__posting_date", "credit"),
    ):
        item = "invoice_line__item_id" if kind == "credit" else "item_id"
        qs = model.objects.filter(**{f"{date_field}__range": (start, end)})
        if filters.get("currency"):
            qs = qs.filter(**{f"{prefix}__currency": filters["currency"]})
        if filters.get("customer_id"):
            qs = qs.filter(**{f"{prefix}__customer_id": filters["customer_id"]})
        if filters.get("item_id"):
            qs = qs.filter(**{item: filters["item_id"]})
        keys = [item, f"{prefix}__currency"]
        rows = qs.values(*keys).annotate(native=Sum("taxable"))
        if kind != "credit":
            rows = rows.annotate(quantity=Sum("quantity"))
        for row in _bounded(rows.order_by(item, f"{prefix}__currency")):
            pk, ccy = row[item], row[f"{prefix}__currency"]
            current = groups.setdefault(
                (pk, ccy),
                {
                    "id": pk,
                    "name": f"Catalog item #{pk}" if pk else "Custom document lines",
                    "currency": ccy,
                    "quantity": ZERO,
                    "net": ZERO,
                    "credits": ZERO,
                    "route": f"/catalog/products/{pk}" if pk else "/sales/invoices",
                },
            )
            if kind == "credit":
                current["credits"] += row["native"] or ZERO
            else:
                sign = 1 if kind == "issued" else -1
                current["quantity"] += (row["quantity"] or ZERO) * sign
                current["net"] += (row["native"] or ZERO) * sign
    for row in groups.values():
        row["net"] -= row["credits"]
    return list(groups.values())


def _vendors(start, end, filters):
    groups = {}
    for model in (VendorBill, Expense):
        for source, sign in (("journal", 1), ("void_journal", -1)):
            qs = model.objects.filter(**{f"{source}__posting_date__range": (start, end)})
            if filters.get("currency"):
                qs = qs.filter(currency=filters["currency"])
            if filters.get("vendor_id"):
                qs = qs.filter(vendor_id=filters["vendor_id"])
            for row in _bounded(
                qs.values("vendor_id", "vendor__name", "currency")
                .annotate(native=Sum("total"), base=Sum("base_total"))
                .order_by("vendor_id", "currency")
            ):
                key = (row["vendor_id"], row["currency"])
                current = groups.setdefault(
                    key,
                    {
                        "id": row["vendor_id"],
                        "name": row["vendor__name"] or "No vendor assigned",
                        "currency": row["currency"],
                        "native": ZERO,
                        "base": ZERO,
                        "route": f"/purchases/vendors/{row['vendor_id']}"
                        if row["vendor_id"]
                        else "/purchases/expenses",
                    },
                )
                current["native"] += (row["native"] or ZERO) * sign
                current["base"] += (row["base"] or ZERO) * sign
    return list(groups.values())


def report_rows(user, which, start, end, company, filters):
    columns = []
    note = ""
    rows = []
    metadata = {}
    if which in ("income", "expense"):
        pnl = reports.report("pnl", start, end)
        kind = "revenue" if which == "income" else "expense"
        rows = [
            {
                "id": r["account_id"],
                "code": r["code"],
                "name": r["name"],
                "amount": r["report_amount"],
                "route": f"/banking/ledger/{r['account_id']}",
            }
            for r in pnl["rows"]
            if r["account_type"] == kind and not r["is_summary"]
        ]
        if filters.get("account_id"):
            rows = [r for r in rows if r["id"] == filters["account_id"]]
        columns = [
            _column("code", "Account"),
            _column("name", "Name"),
            _column("amount", "Posted net amount", "base_money"),
        ]
        note = (
            "Posted GL only. Hierarchy subtotal rows are excluded from "
            "aggregation; reversals and reclassifications remain included."
        )
    elif which in ("ar", "ap"):
        result = aging(which, end)
        rows = result.pop("rows")
        metadata = result
        if filters.get("customer_id") or filters.get("vendor_id"):
            party = filters.get("customer_id") or filters.get("vendor_id")
            rows = [r for r in rows if r["party_id"] == party]
            metadata["filtered_aged_total"] = sum((r["base_outstanding"] for r in rows), ZERO)
        columns = [
            _column("number", "Source"),
            _column("party", "Counterparty"),
            _column("due_date", "Due date", "date"),
            _column("bucket", "Age bucket"),
            _column("base_outstanding", "Historical base outstanding", "base_money"),
        ]
        note = (
            "As-of posted control lines, including dated reversals. "
            "Unallocated/opening balances are disclosed separately and "
            "reconcile to the full GL control."
        )
    elif which == "customer":
        rows = _customer_rows(start, end, filters)
        columns = [
            _column("name", "Customer"),
            _column("currency", "Currency"),
            _column("issued", "Gross invoiced", "money"),
            _column("credited", "Credit notes", "money"),
            _column("voided", "Voided gross", "money"),
            _column("net", "Net invoiced incl. tax", "money"),
            _column("base_net", "Historical base invoicing", "base_money"),
        ]
        note = (
            "Invoice, credit and void events by their actual posting dates. "
            "Invoicing includes tax; it is separate from recognized revenue "
            "and collected cash."
        )
    elif which == "product":
        rows = _product_rows(start, end, filters)
        columns = [
            _column("name", "Stable catalog identity"),
            _column("currency", "Currency"),
            _column("quantity", "Quantity invoiced", "quantity"),
            _column("credits", "Net credit amount", "money"),
            _column("net", "Net invoiced excl. tax", "money"),
        ]
        note = (
            "Frozen document quantities and prices, grouped by stable item "
            "identity and currency. Amount credits do not imply physically "
            "returned quantities. Current catalog prices are never "
            "substituted."
        )
    elif which == "vendors":
        rows = _vendors(start, end, filters)
        columns = [
            _column("name", "Vendor"),
            _column("currency", "Currency"),
            _column("native", "Acquisition / expense sources", "money"),
            _column("base", "Historical base source total", "base_money"),
        ]
        note = (
            "Original posted purchasing sources net of voids, including taxes "
            "and capital acquisitions. This is acquisition analysis; see P&L "
            "for recognized expenses after source-owned reclassification."
        )
    elif which == "locations":
        qs = Movement.objects.filter(date__lte=end)
        if filters.get("location_id"):
            qs = qs.filter(location_id=filters["location_id"])
        if filters.get("item_id"):
            qs = qs.filter(item_id=filters["item_id"])
        rows = [
            {
                "id": f"{r['item_id']}:{r['location_id']}",
                "item": r["item__name"],
                "code": r["item__code"],
                "location": r["location__name"],
                "unit": r["item__unit"],
                "quantity": r["quantity"],
                "route": f"/inventory/items/{r['item_id']}",
            }
            for r in _bounded(
                qs.values(
                    "item_id",
                    "item__name",
                    "item__code",
                    "item__unit",
                    "location_id",
                    "location__name",
                )
                .annotate(quantity=Sum("quantity"))
                .order_by("item__code", "location__code")
            )
        ]
        columns = [
            _column("code", "SKU"),
            _column("item", "Product"),
            _column("location", "Company-owned location"),
            _column("unit", "Unit"),
            _column("quantity", "On hand", "quantity"),
        ]
        note = (
            "As-of location quantities. Monetary inventory valuation uses one "
            "company-wide cost pool; location values are not independent "
            "ledgers."
        )
    elif which == "low-stock":
        qs = (
            ItemProfile.objects.filter(kind="stock", item__is_active=True)
            .select_related("item", "unit")
            .annotate(
                on_hand=Sum(
                    "item__stock_moves__quantity", filter=Q(item__stock_moves__date__lte=end)
                )
            )
        )
        if filters.get("item_id"):
            qs = qs.filter(item_id=filters["item_id"])
        for item in _bounded(qs.order_by("item__code")):
            if (item.on_hand or ZERO) <= item.reorder_level:
                rows.append(
                    {
                        "id": item.item_id,
                        "code": item.item.code,
                        "name": item.item.name,
                        "unit": item.unit.code,
                        "on_hand": item.on_hand or ZERO,
                        "reorder": item.reorder_level,
                        "route": f"/inventory/items/{item.item_id}",
                    }
                )
        columns = [
            _column("code", "SKU"),
            _column("name", "Product"),
            _column("unit", "Unit"),
            _column("on_hand", "On hand", "quantity"),
            _column("reorder", "Reorder threshold", "quantity"),
        ]
        note = (
            "Configured reorder thresholds and actual as-of quantities. "
            "Different units are not combined into a misleading total."
        )
    elif which == "receiving":
        qs = GoodsReceipt.objects.filter(date__range=(start, end)).select_related(
            "order_line__order__vendor", "order_line__item"
        )
        if filters.get("vendor_id"):
            qs = qs.filter(order_line__order__vendor_id=filters["vendor_id"])
        if filters.get("location_id"):
            qs = qs.filter(location_id=filters["location_id"])
        if filters.get("item_id"):
            qs = qs.filter(order_line__item_id=filters["item_id"])
        for receipt in _bounded(qs.order_by("-date", "-pk")):
            rows.append(
                {
                    "id": receipt.pk,
                    "date": receipt.date,
                    "reference": receipt.reference,
                    "order": receipt.order_line.order.number,
                    "vendor": receipt.order_line.order.vendor.name,
                    "item": receipt.order_line.item.name,
                    "kind": receipt.kind,
                    "quantity": receipt.quantity,
                    "rejected": receipt.rejected_quantity,
                    "base_cost": receipt.base_value,
                    "route": f"/purchases/orders/{receipt.order_line.order_id}",
                }
            )
        columns = [
            _column("date", "Accepted date", "date"),
            _column("reference", "Evidence reference"),
            _column("order", "Purchase order"),
            _column("vendor", "Vendor"),
            _column("item", "Item"),
            _column("kind", "Acceptance"),
            _column("quantity", "Accepted", "quantity"),
            _column("rejected", "Rejected", "quantity"),
            _column("base_cost", "Original historical base cost", "base_money"),
        ]
        note = (
            "Accepted source receipts; retained acquisition corrections "
            "remain separate from the immutable original receipt value. "
            "Service acceptance does not create warehouse stock."
        )
    elif which == "history":
        from apps.accounting.models import HistoricalRecord
        from apps.accounting.services.onboarding import visible_records

        qs = visible_records(
            user,
            HistoricalRecord.objects.filter(
                Q(original_date__range=(start, end))
                | Q(treatments__recognition_date__range=(start, end))
            ).distinct(),
        ).prefetch_related("treatments")
        if filters.get("currency"):
            qs = qs.filter(currency=filters["currency"])
        for obj in _bounded(qs.order_by("-original_date", "-pk")):
            treatment = obj.treatments.order_by("-pk").first()
            rows.append(
                {
                    "id": obj.pk,
                    "reference": obj.external_reference,
                    "original_date": obj.original_date,
                    "description": obj.description,
                    "currency": obj.currency,
                    "amount": obj.amount,
                    "funding": obj.funding_classification,
                    "pre_registration": obj.pre_registration,
                    "mode": treatment.mode if treatment else "evidence_only",
                    "recognition_date": treatment.recognition_date if treatment else None,
                    "review": treatment.status if treatment else "not_requested",
                    "route": "/purchases/onboarding",
                }
            )
        columns = [
            _column("reference", "Original reference"),
            _column("original_date", "Original date", "date"),
            _column("recognition_date", "Recognition / linked date", "date"),
            _column("funding", "Funding distinction"),
            _column("currency", "Currency"),
            _column("amount", "Documented amount", "money"),
            _column("mode", "Provenance"),
            _column("review", "Review"),
        ]
        note = (
            "Evidence-only, reconstructed drafts, opening-only balances and "
            "linked verified sources remain distinct. This report never adds "
            "these records together as recognized expenses."
        )
    elif which == "recurring":
        qs = (
            RecurringInvoiceSchedule.objects.select_related("customer")
            .filter(status="active", start_date__lte=end)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=end))
        )
        if filters.get("customer_id"):
            qs = qs.filter(customer_id=filters["customer_id"])
        if filters.get("currency"):
            qs = qs.filter(currency=filters["currency"])
        for obj in _bounded(qs.order_by("pk")):
            net = None
            pricing_status = "Current template priced"
            try:
                template = obj.template
                result = calculation.calculate(
                    currency=obj.currency,
                    on=end,
                    prices_include_tax=template.get("prices_include_tax", False),
                    discount_type=template.get("discount_type", "percent"),
                    discount_value=template.get("discount_value", "0"),
                    lines=template["lines"],
                )
                with localcontext() as context:
                    context.prec = 60
                    factors = {
                        "weekly": Decimal(52) / 12,
                        "monthly": Decimal(1),
                        "quarterly": Decimal(1) / 3,
                        "yearly": Decimal(1) / 12,
                    }
                    net = (result["taxable"] * factors[obj.frequency] / obj.interval).quantize(
                        quantum(obj.currency), rounding=ROUND_HALF_UP
                    )
            except ValidationError:
                pricing_status = (
                    "Current tax/template configuration requires review; no run rate assumed"
                )
            issued = Invoice.objects.filter(recurring_run__schedule=obj)
            invoices_native = _sum(
                issued.filter(journal__posting_date__range=(start, end)), "taxable"
            ) - _sum(issued.filter(void_journal__posting_date__range=(start, end)), "taxable")
            credit_native = _sum(
                CreditNote.objects.filter(
                    invoice__recurring_run__schedule=obj, journal__posting_date__range=(start, end)
                ),
                "taxable",
            )
            rows.append(
                {
                    "id": obj.pk,
                    "customer": obj.customer.name,
                    "currency": obj.currency,
                    "frequency": f"{obj.interval} × {obj.frequency}",
                    "run_rate": net,
                    "actual_invoiced": invoices_native - credit_native,
                    "pricing_status": pricing_status,
                    "next_date": obj.next_run_date,
                    "route": "/sales/recurring",
                }
            )
        columns = [
            _column("customer", "Customer"),
            _column("currency", "Currency"),
            _column("frequency", "Current schedule"),
            _column("run_rate", "Normalized monthly net invoicing run rate", "money"),
            _column("actual_invoiced", "Actual net invoiced in range", "money"),
            _column("pricing_status", "Pricing basis"),
            _column("next_date", "Next due", "date"),
        ]
        note = (
            "Current schedule configuration, excluding tax; weekly "
            "normalization uses 52/12, quarterly 1/3 and yearly 1/12. This is "
            "contracted invoicing run rate, not recognized revenue, actual "
            "invoices or collections."
        )
    elif which == "bank":
        from apps.accounting.models import JournalLine

        qs = JournalLine.objects.filter(
            journal__status="posted",
            journal__posting_date__range=(start, end),
            account__bank_account__isnull=False,
        ).select_related("journal", "account__bank_account")
        if filters.get("account_id"):
            qs = qs.filter(account_id=filters["account_id"])
        if filters.get("currency"):
            qs = qs.filter(currency=filters["currency"])
        for line in _bounded(qs.order_by("-journal__posting_date", "-pk")):
            rows.append(
                {
                    "id": line.pk,
                    "date": line.journal.posting_date,
                    "number": line.journal.number,
                    "account": line.account.bank_account.name,
                    "kind": line.journal.kind,
                    "currency": line.currency,
                    "debit": line.debit,
                    "credit": line.credit,
                    "base_debit": line.base_debit,
                    "base_credit": line.base_credit,
                    "route": f"/banking/journals/{line.journal_id}",
                }
            )
        columns = [
            _column("date", "Date", "date"),
            _column("number", "Journal"),
            _column("account", "Cash / bank account"),
            _column("kind", "Source treatment"),
            _column("currency", "Currency"),
            _column("debit", "Debit", "money"),
            _column("credit", "Credit", "money"),
            _column("base_debit", "Historical base debit", "base_money"),
            _column("base_credit", "Historical base credit", "base_money"),
        ]
        note = (
            "Actual posted cash/bank legs, including both sides of internal "
            "transfers. Cash-flow reporting eliminates internal movements "
            "separately. Private bank evidence is not included in this "
            "report."
        )
    elif which == "tax":
        from apps.accounting.models import JournalLine, TaxRevision

        ids = set(TaxRevision.objects.values_list("input_account_id", flat=True)) | set(
            TaxRevision.objects.values_list("output_account_id", flat=True)
        )
        qs = JournalLine.objects.filter(
            journal__status="posted", journal__posting_date__lte=end, account_id__in=ids
        )
        if filters.get("account_id"):
            qs = qs.filter(account_id=filters["account_id"])
        for row in _bounded(
            qs.values("account_id", "account__code", "account__name", "account__account_type")
            .annotate(
                debit=Sum("base_debit", filter=Q(journal__posting_date__gte=start)),
                credit=Sum("base_credit", filter=Q(journal__posting_date__gte=start)),
                balance=Sum(F("base_debit") - F("base_credit")),
            )
            .order_by("account__code")
        ):
            rows.append(
                {
                    "id": row["account_id"],
                    "code": row["account__code"],
                    "name": row["account__name"],
                    "kind": "Recoverable input tax"
                    if row["account__account_type"] == "asset"
                    else "Output tax",
                    "debit": row["debit"] or ZERO,
                    "credit": row["credit"] or ZERO,
                    "balance": row["balance"]
                    if row["account__account_type"] == "asset"
                    else -row["balance"],
                    "route": f"/banking/ledger/{row['account_id']}",
                }
            )
        columns = [
            _column("code", "Account"),
            _column("name", "Name"),
            _column("kind", "Tax position"),
            _column("debit", "Period debit", "base_money"),
            _column("credit", "Period credit", "base_money"),
            _column("balance", "Closing tax position", "base_money"),
        ]
        note = (
            "Configured input/output tax accounts from posted GL. Closing "
            "position includes prior activity; period movements use the "
            "selected range. Tax calculations and statutory filing remain "
            "separate source-owned workflows."
        )
    else:
        raise BusinessRuleViolation(
            "Open this report in its linked owning workflow.", code="owning_report"
        )
    term = filters.get("search", "").strip().casefold()
    if term:
        rows = [
            row
            for row in rows
            if term in " ".join(str(v) for k, v in row.items() if k != "route").casefold()
        ]
    _bounded(rows)
    order = filters.get("sort", "")
    if order:
        key = order.removeprefix("-")
        if key not in {column["key"] for column in columns}:
            raise ValidationError({"sort": "Choose a displayed report column."})
        # Sort exact native values before string serialization; nulls stay last.
        present = [row for row in rows if row.get(key) is not None]
        missing = [row for row in rows if row.get(key) is None]
        numeric = next(column["kind"] for column in columns if column["key"] == key) in (
            "money",
            "base_money",
            "quantity",
        )

        def sort_value(row):
            value = row[key]
            if numeric:
                return Decimal(value)
            return value.casefold() if isinstance(value, str) else value

        rows = (
            sorted(
                present,
                key=sort_value,
                reverse=order.startswith("-"),
            )
            + missing
        )
    return strings(
        {
            "report": which,
            "from": start,
            "to": end,
            "base_currency": company.base_currency,
            "columns": columns,
            "rows": rows,
            "note": note,
            "summary": metadata,
        }
    )
