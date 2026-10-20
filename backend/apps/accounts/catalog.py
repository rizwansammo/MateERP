"""Stable application permission codes and default roles.

Codes are part of the API contract: future modules check them by name, so
never rename or reuse a code. Add new codes here and in a data migration
(``sync_permission_catalog`` runs after every migrate as well).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    code: str
    label: str
    category: str
    description: str = ""


CATEGORIES: dict[str, str] = {
    "administration": "Administration",
    "finance": "Finance",
    "founder": "Founder Finance",
    "operations": "Operations",
}

PERMISSIONS: tuple[PermissionDef, ...] = (
    # Administration
    PermissionDef("company.view", "View company settings", "administration"),
    PermissionDef(
        "company.edit",
        "Edit company settings",
        "administration",
        "Company profile, financial, currency, tax and module settings.",
    ),
    PermissionDef(
        "branding.manage",
        "Manage company branding",
        "administration",
        "Invoice and receipt branding, signature and seal.",
    ),
    PermissionDef("users.manage", "Manage users", "administration"),
    PermissionDef("roles.manage", "Manage roles", "administration"),
    PermissionDef("permissions.manage", "Manage permissions", "administration"),
    PermissionDef("approvals.manage", "Manage approval rules", "administration"),
    PermissionDef("audit.view", "View audit logs", "administration"),
    # Finance
    PermissionDef("finance.view", "View financial records", "finance"),
    PermissionDef("accounting.manage", "Manage accounting", "finance"),
    PermissionDef("accounting.approve", "Approve financial adjustments", "finance"),
    PermissionDef("accounting.periods.manage", "Close and reopen accounting periods", "finance"),
    PermissionDef("invoices.create", "Create invoices", "finance"),
    PermissionDef("payments.approve", "Approve payments", "finance"),
    PermissionDef("expenses.manage", "Manage expenses", "finance"),
    PermissionDef("banking.evidence.view", "View banking evidence", "finance"),
    PermissionDef("reports.export", "Export financial reports", "finance"),
    # Founder finance
    PermissionDef("founder.view", "View founder finance", "founder"),
    PermissionDef("founder.transactions.manage", "Manage founder transactions", "founder"),
    PermissionDef("founder.settlements.manage", "Manage founder settlements", "founder"),
    PermissionDef("ownership.manage", "Manage ownership records", "founder"),
    # Operations
    PermissionDef("procurement.manage", "Manage procurement", "operations"),
    PermissionDef("inventory.manage", "Manage inventory", "operations"),
    PermissionDef("assets.manage", "Manage fixed assets", "operations"),
    PermissionDef("budgets.manage", "Manage budgets", "operations"),
)

ALL_CODES: frozenset[str] = frozenset(p.code for p in PERMISSIONS)

ADMIN_ROLE_KEY = "administrator"


@dataclass(frozen=True)
class RoleDef:
    key: str
    name: str
    description: str
    permissions: frozenset[str]
    is_admin: bool = False


_FINANCE_MANAGER = ALL_CODES - {
    "accounting.approve",
    "accounting.periods.manage",
    "users.manage",
    "roles.manage",
    "permissions.manage",
    "ownership.manage",
}

DEFAULT_ROLES: tuple[RoleDef, ...] = (
    RoleDef(
        ADMIN_ROLE_KEY,
        "Administrator",
        "Full access to every module and setting.",
        ALL_CODES,
        is_admin=True,
    ),
    RoleDef(
        "finance_manager",
        "Finance Manager",
        "Runs billing, payments, accounting and approvals.",
        frozenset(_FINANCE_MANAGER),
    ),
    RoleDef(
        "accountant",
        "Accountant",
        "Records transactions and journals; no approvals.",
        frozenset(
            {
                "finance.view",
                "invoices.create",
                "expenses.manage",
                "accounting.manage",
                "banking.evidence.view",
                "reports.export",
                "company.view",
            }
        ),
    ),
    RoleDef(
        "operations_manager",
        "Operations Manager",
        "Procurement, inventory and assets. No financial records.",
        frozenset({"procurement.manage", "inventory.manage", "assets.manage", "expenses.manage"}),
    ),
    RoleDef(
        "viewer", "Viewer", "Read-only access to financial records.", frozenset({"finance.view"})
    ),
)
