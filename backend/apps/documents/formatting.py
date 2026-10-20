"""Document text formatting (amounts, quantities, dates, amounts in words).

Mirrors the browser presentation in ``features/documents/money.ts`` so a PDF reads
exactly like the on-screen document: grouping (international or lakh/crore), symbol
or code display and currency minor units. Values arrive as exact decimal strings.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.company.reference import CURRENCIES

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"]


def _group(whole: str, grouping: str) -> str:
    if grouping != "south_asian" or len(whole) <= 3:
        return f"{int(whole):,}"
    last3, rest = whole[-3:], whole[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return ",".join(parts + [last3])


def number(value, currency: str, grouping: str = "international") -> str:
    minor = CURRENCIES[currency].minor_units
    amount = Decimal(str(value)).quantize(Decimal(10) ** -minor, rounding=ROUND_HALF_UP)
    sign = "−" if amount < 0 else ""
    whole, _, frac = format(abs(amount), "f").partition(".")
    text = _group(whole, grouping)
    return f"{sign}{text}.{frac}" if minor else f"{sign}{text}"


def money(value, fmt: dict) -> str:
    text = number(value, fmt["currency"], fmt.get("grouping", "international"))
    if fmt.get("display") == "symbol":
        return f"{fmt.get('symbol') or fmt['currency']}{text}"
    return f"{fmt['currency']} {text}"


def quantity(value) -> str:
    d = Decimal(str(value)).normalize()
    return format(d, "f") if d == d.to_integral() else format(d, "f").rstrip("0")


def percent(value) -> str:
    d = Decimal(str(value)).normalize()
    return f"{format(d.quantize(Decimal(1)) if d == d.to_integral() else d, 'f')}%"


def day(value) -> str:
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


ONES = (
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
)
TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")
CURRENCY_WORDS = {
    "BDT": ("Taka", "Poisha"),
    "USD": ("US Dollars", "Cents"),
    "EUR": ("Euros", "Cents"),
    "GBP": ("Pounds Sterling", "Pence"),
    "SGD": ("Singapore Dollars", "Cents"),
    "INR": ("Rupees", "Paise"),
}


def _below_hundred(n: int) -> str:
    if n < 20:
        return ONES[n]
    return f"{TENS[n // 10]}-{ONES[n % 10]}" if n % 10 else TENS[n // 10]


def _below_thousand(n: int) -> str:
    parts = []
    if n // 100:
        parts.append(f"{ONES[n // 100]} Hundred")
    if n % 100:
        parts.append(_below_hundred(n % 100))
    return " ".join(parts)


def _whole_words(n: int, south_asian: bool) -> str:
    if n < 1000:
        return _below_thousand(n) or "Zero"
    scales = (
        ((10_000_000, "Crore"), (100_000, "Lakh"), (1000, "Thousand"))
        if south_asian
        else (
            (10**18, "Quintillion"),
            (10**15, "Quadrillion"),
            (10**12, "Trillion"),
            (10**9, "Billion"),
            (10**6, "Million"),
            (1000, "Thousand"),
        )
    )
    parts = []
    for size, name in scales:
        count, n = divmod(n, size)
        if count:
            parts.append(f"{_whole_words(count, south_asian)} {name}")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def in_words(value, currency: str) -> str:
    """Amount in words; lakh/crore scales for BDT and INR."""
    minor_units = CURRENCIES[currency].minor_units
    amount = abs(Decimal(str(value)))
    n = int(amount)
    fraction = int((amount - n) * (10**minor_units)) if minor_units else 0
    words = _whole_words(n, currency in ("BDT", "INR"))
    major, minor_name = CURRENCY_WORDS.get(currency, (currency, "Cents"))
    tail = f" and {_below_hundred(fraction)} {minor_name}" if fraction and fraction < 100 else ""
    return f"Taka {words}{tail} Only" if currency == "BDT" else f"{words} {major}{tail} Only"
