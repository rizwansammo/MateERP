"""Finite Decimal amounts; one explicit conversion rounding policy."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from rest_framework.exceptions import ValidationError

from apps.company.reference import CURRENCIES

ZERO = Decimal("0")


def decimal(value, field="amount", scale=6, *, signed=False):
    if isinstance(value, float | bool):
        raise ValidationError({field: "Use a decimal string, never a floating-point number."})
    try:
        result = Decimal(value)
        if not result.is_finite() or (not signed and result < 0):
            raise InvalidOperation
        if result.as_tuple().exponent < -scale or abs(result) >= Decimal(10) ** 18:
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(
            {
                field: (
                    f"Enter a finite {'signed ' if signed else 'nonnegative '}decimal "
                    f"with at most {scale} places."
                )
            }
        ) from None


def quantum(currency):
    if currency not in CURRENCIES:
        raise ValidationError({"currency": "Unsupported currency."})
    return Decimal(10) ** -CURRENCIES[currency].minor_units


def money(value, currency, field="amount", *, signed=False):
    value = decimal(value, field, signed=signed)
    if value != value.quantize(quantum(currency)):
        raise ValidationError({field: f"Too many decimal places for {currency}."})
    return value


def convert(value, fx, currency):
    with localcontext() as ctx:
        ctx.prec = 60
        result = (value * fx).quantize(quantum(currency), rounding=ROUND_HALF_UP)
        if abs(result) >= Decimal(10) ** 18:
            raise ValidationError(
                {"amount": "Converted amount exceeds the supported storage range."}
            )
        return result


def strings(value):
    """JSON-compatible financial snapshots without float conversion."""
    from datetime import date, datetime
    from uuid import UUID

    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date | datetime | UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: strings(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [strings(v) for v in value]
    return value
