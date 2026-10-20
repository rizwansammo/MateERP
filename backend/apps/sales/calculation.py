"""Exact commercial-document arithmetic. The server is authoritative; clients only display.

Order of operations (every rounding is ROUND_HALF_UP to the currency's minor unit):

1. Line subtotal  = round(quantity × unit price).
2. Line discount  = round(subtotal × percent / 100), or a fixed amount ≤ subtotal.
   Line amount    = subtotal − line discount.
3. Document discount = round(Σ line amounts × percent / 100), or a fixed amount ≤ Σ line
   amounts. It is allocated to lines in proportion to their line amounts using largest
   remainders in minor units, so the allocations sum to the discount exactly
   (ties go to the earlier line).
4. Tax, per line, using the tax code's revision effective on the document date:
   - tax-exclusive prices: taxable = line amount − allocated discount;
     tax = round(taxable × rate / 100);
   - tax-inclusive prices: gross = line amount − allocated discount;
     taxable = round(gross × 100 / (100 + rate)); tax = gross − taxable.
5. Line total = taxable + tax. Document total = Σ line totals.

Tax per code is the sum of its line taxes, so the breakdown always equals the total tax.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, localcontext

from rest_framework.exceptions import ValidationError

from apps.accounting.models import TaxRevision
from apps.accounting.money import ZERO, decimal, money, quantum

HUNDRED = Decimal(100)
MAX_LINES = 250


def _round(value, currency, rounding=ROUND_HALF_UP):
    with localcontext() as ctx:
        ctx.prec = 60
        return value.quantize(quantum(currency), rounding=rounding)


def _discount(base, kind, value, currency, field):
    if kind not in ("percent", "fixed"):
        raise ValidationError({field: "Choose a percent or fixed discount."})
    if kind == "percent":
        pct = decimal(value or "0", field, 6)
        if pct > HUNDRED:
            raise ValidationError({field: "A percentage discount cannot exceed 100%."})
        with localcontext() as ctx:
            ctx.prec = 60
            return _round(base * pct / HUNDRED, currency)
    fixed = money(value or "0", currency, field)
    if fixed > base:
        raise ValidationError({field: "A fixed discount cannot exceed the amount it reduces."})
    return fixed


def allocate(total, weights, currency):
    """Split ``total`` across ``weights`` exactly, by largest remainder in minor units."""
    unit = quantum(currency)
    weight_sum = sum(weights, ZERO)
    if total == 0 or weight_sum == 0:
        return [ZERO for _ in weights]
    with localcontext() as ctx:
        ctx.prec = 60
        raw = [total * w / weight_sum for w in weights]
        floors = [_round(r, currency, ROUND_DOWN) for r in raw]
        left = int((total - sum(floors, ZERO)) / unit)
        order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - floors[i]), i))
        for i in order[:left]:
            floors[i] += unit
    return floors


def tax_revision(tax_code_id, on):
    revision = (
        TaxRevision.objects.select_related("tax_code")
        .filter(tax_code_id=tax_code_id, effective_date__lte=on)
        .order_by("-effective_date", "-pk")
        .first()
    )
    if revision is None or not revision.tax_code.is_active:
        raise ValidationError(
            {"tax_code_id": f"The tax code has no active rate effective on {on}."}
        )
    return revision


def calculate(
    *,
    currency,
    on,
    lines,
    prices_include_tax=False,
    discount_type="percent",
    discount_value="0",
):
    """Return exact line amounts, tax breakdown and totals for a commercial document."""
    quantum(currency)
    if not isinstance(lines, list) or not 1 <= len(lines) <= MAX_LINES:
        raise ValidationError({"lines": f"Provide between 1 and {MAX_LINES} lines."})
    out = []
    for index, line in enumerate(lines, 1):
        field = f"lines.{index}"
        qty = decimal(line.get("quantity", "1"), f"{field}.quantity", 6)
        price = decimal(line.get("unit_price", "0"), f"{field}.unit_price", 6)
        if qty <= 0:
            raise ValidationError({f"{field}.quantity": "Quantity must be positive."})
        with localcontext() as ctx:
            ctx.prec = 60
            subtotal = _round(qty * price, currency)
        line_discount = _discount(
            subtotal,
            line.get("discount_type", "percent"),
            line.get("discount_value", "0"),
            currency,
            f"{field}.discount_value",
        )
        revision = tax_revision(line["tax_code_id"], on) if line.get("tax_code_id") else None
        out.append(
            {
                "position": index,
                "quantity": qty,
                "unit_price": price,
                "subtotal": subtotal,
                "line_discount": line_discount,
                "amount": subtotal - line_discount,
                "revision": revision,
            }
        )
    base = sum((x["amount"] for x in out), ZERO)
    document_discount = _discount(base, discount_type, discount_value, currency, "discount_value")
    shares = allocate(document_discount, [x["amount"] for x in out], currency)
    breakdown = {}
    for line, share in zip(out, shares, strict=True):
        revision = line.pop("revision")
        gross = line["amount"] - share
        rate = revision.percent if revision else ZERO
        with localcontext() as ctx:
            ctx.prec = 60
            if prices_include_tax:
                taxable = _round(gross * HUNDRED / (HUNDRED + rate), currency)
                tax = gross - taxable
            else:
                taxable = gross
                tax = _round(taxable * rate / HUNDRED, currency)
        line.update(
            document_discount=share,
            taxable=taxable,
            tax=tax,
            total=taxable + tax,
            tax_rate=rate,
            tax_revision_id=revision.pk if revision else None,
            tax_code_id=revision.tax_code_id if revision else None,
        )
        if revision:
            entry = breakdown.setdefault(
                revision.pk,
                {
                    "tax_revision_id": revision.pk,
                    "tax_code_id": revision.tax_code_id,
                    "code": revision.tax_code.code,
                    "rate": rate,
                    "taxable": ZERO,
                    "tax": ZERO,
                },
            )
            entry["taxable"] += taxable
            entry["tax"] += tax
    return {
        "currency": currency,
        "prices_include_tax": bool(prices_include_tax),
        "lines": out,
        "taxes": list(breakdown.values()),
        "subtotal": sum((x["subtotal"] for x in out), ZERO),
        "line_discount": sum((x["line_discount"] for x in out), ZERO),
        "document_discount": document_discount,
        "taxable": sum((x["taxable"] for x in out), ZERO),
        "tax": sum((x["tax"] for x in out), ZERO),
        "total": sum((x["total"] for x in out), ZERO),
    }
