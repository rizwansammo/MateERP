"""Approval policy categories.

Only categories whose owning feature exists are *enforced*. The others are
stored configuration that their module will enforce when it is delivered;
the UI labels them honestly.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyCategory:
    key: str
    label: str
    description: str
    phase: int
    enforced: bool
    supports_threshold: bool


CATEGORIES: tuple[PolicyCategory, ...] = (
    PolicyCategory(
        "admin_changes",
        "Sensitive administrative changes",
        "Publishing invoice & receipt branding. More administrative actions can be covered later.",
        2,
        True,
        False,
    ),
    PolicyCategory("expenses", "Expenses", "Expenses at or above the threshold.", 4, False, True),
    PolicyCategory(
        "purchase_orders",
        "Purchase orders",
        "Purchase orders at or above the threshold.",
        6,
        False,
        True,
    ),
    PolicyCategory(
        "client_payments",
        "Client payments",
        "Verification of recorded client payments.",
        4,
        False,
        True,
    ),
    PolicyCategory(
        "financial_adjustments",
        "Financial adjustments",
        "Manual journals and adjustments at or above the threshold.",
        3,
        True,
        True,
    ),
    PolicyCategory(
        "ownership_changes",
        "Ownership changes",
        "Share transfers, issuance and capital changes.",
        5,
        False,
        False,
    ),
)
BY_KEY = {c.key: c for c in CATEGORIES}

# action code -> policy category
ACTIONS: dict[str, str] = {
    "branding.publish": "admin_changes",
    "accounting.post": "financial_adjustments",
}
