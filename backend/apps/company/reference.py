"""Reference data: currencies, optional modules and document numbering keys."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Currency:
    code: str
    name: str
    symbol: str
    minor_units: int


CURRENCIES: dict[str, Currency] = {
    c.code: c
    for c in (
        Currency("BDT", "Bangladeshi Taka", "৳", 2),
        Currency("USD", "US Dollar", "$", 2),
        Currency("EUR", "Euro", "€", 2),
        Currency("GBP", "Pound Sterling", "£", 2),
        Currency("SGD", "Singapore Dollar", "S$", 2),
        Currency("INR", "Indian Rupee", "₹", 2),
        Currency("AED", "UAE Dirham", "د.إ", 2),
        Currency("SAR", "Saudi Riyal", "﷼", 2),
        Currency("MYR", "Malaysian Ringgit", "RM", 2),
        Currency("AUD", "Australian Dollar", "A$", 2),
        Currency("CAD", "Canadian Dollar", "C$", 2),
        Currency("CHF", "Swiss Franc", "CHF", 2),
        Currency("CNY", "Chinese Yuan", "¥", 2),
        Currency("JPY", "Japanese Yen", "¥", 0),
        Currency("HKD", "Hong Kong Dollar", "HK$", 2),
        Currency("PKR", "Pakistani Rupee", "₨", 2),
        Currency("LKR", "Sri Lankan Rupee", "Rs", 2),
        Currency("NPR", "Nepalese Rupee", "Rs", 2),
        Currency("THB", "Thai Baht", "฿", 2),
        Currency("NZD", "New Zealand Dollar", "NZ$", 2),
        Currency("SEK", "Swedish Krona", "kr", 2),
        Currency("KRW", "South Korean Won", "₩", 0),
    )
}


@dataclass(frozen=True)
class ModuleDef:
    key: str
    label: str
    description: str
    phase: int
    nav_id: str


# Optional business modules. Core accounting, sales & billing, documents,
# authentication, permissions and audit are always on and not listed here.
OPTIONAL_MODULES: tuple[ModuleDef, ...] = (
    ModuleDef(
        "founder",
        "Founder Finance",
        "Founder contributions, expenses, settlements and loans.",
        5,
        "founder",
    ),
    ModuleDef(
        "ownership",
        "Ownership & Capital",
        "Shareholders, capital records and transfers.",
        5,
        "ownership",
    ),
    ModuleDef(
        "procurement",
        "Procurement (Purchase Orders)",
        "Purchase orders, approval and receiving.",
        6,
        "purchases/orders",
    ),
    ModuleDef(
        "inventory",
        "Inventory & Warehouse",
        "Items, stock movements and valuation.",
        6,
        "inventory",
    ),
    ModuleDef("assets", "Fixed Assets", "Asset register, depreciation and disposal.", 6, "assets"),
    ModuleDef(
        "budgeting",
        "Budgets & Cost Centers",
        "Budgets, cost centres and comparisons.",
        6,
        "budgets",
    ),
)
MODULE_KEYS = frozenset(m.key for m in OPTIONAL_MODULES)

CORE_MODULES: tuple[str, ...] = (
    "Core accounting",
    "Sales & billing",
    "Documents",
    "Authentication, permissions & audit",
)

NUMBERING_KEYS: dict[str, str] = {
    "invoice": "Invoice",
    "receipt": "Money receipt",
    "credit_note": "Credit note",
    "payment": "Client payment",
    "expense": "Expense",
    "vendor_bill": "Vendor bill",
    "purchase_order": "Purchase order",
    "journal": "Journal entry",
}

DEFAULT_NUMBERING: dict[str, str] = {
    "invoice": "INV-{YYYY}-{####}",
    "receipt": "MR-{YYYY}-{####}",
    "credit_note": "CN-{YYYY}-{###}",
    "payment": "PAY-{YYYY}-{####}",
    "expense": "EXP-{YYYY}-{####}",
    "vendor_bill": "BILL-{YYYY}-{###}",
    "purchase_order": "PO-{YYYY}-{###}",
    "journal": "JV-{YYYY}-{####}",
}
