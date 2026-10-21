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
    PolicyCategory(
        "expenses",
        "Expenses & vendor bills",
        "Posting expenses and vendor bills at or above the threshold.",
        4,
        True,
        True,
    ),
    PolicyCategory(
        "invoices",
        "Client invoices",
        "Approving client invoices at or above the threshold before issue.",
        4,
        True,
        True,
    ),
    PolicyCategory(
        "credits_refunds",
        "Credit notes & refunds",
        "Issuing credit notes and paying refunds at or above the threshold.",
        4,
        True,
        True,
    ),
    PolicyCategory(
        "vendor_payments",
        "Vendor payments",
        "Paying vendors at or above the threshold.",
        4,
        True,
        True,
    ),
    PolicyCategory(
        "purchase_orders",
        "Purchase orders",
        "Purchase orders at or above the threshold.",
        6,
        True,
        True,
    ),
    PolicyCategory(
        "client_payments",
        "Client payments",
        "Verification of recorded client payments at or above the threshold.",
        4,
        True,
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
        True,
        False,
    ),
)
BY_KEY = {c.key: c for c in CATEGORIES}

# action code -> policy category
ACTIONS: dict[str, str] = {
    "stock_count.post": "financial_adjustments",
    "receipt_cost.post": "financial_adjustments",
    "supplier_return.post": "financial_adjustments",
    "asset.post": "financial_adjustments",
    "budget.publish": "financial_adjustments",
    "historical.review": "financial_adjustments",
    "purchase_order.approve": "purchase_orders",
    "ownership.review": "ownership_changes",
    "founder.post": "financial_adjustments",
    "founder.policy": "admin_changes",
    "branding.publish": "admin_changes",
    "accounting.post": "financial_adjustments",
    "invoice.approve": "invoices",
    "payment.verify": "client_payments",
    "credit_note.issue": "credits_refunds",
    "refund.pay": "credits_refunds",
    "vendor_bill.post": "expenses",
    "expense.post": "expenses",
    "vendor_payment.post": "vendor_payments",
}
