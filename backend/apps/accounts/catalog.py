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
    PermissionDef(
        "sales.manage",
        "Manage customers and sales orders",
        "finance",
        "Customers, contacts, projects, billing items and sales orders.",
    ),
    PermissionDef("invoices.create", "Create invoices", "finance", "Create and edit drafts."),
    PermissionDef(
        "invoices.issue",
        "Approve and issue invoices",
        "finance",
        "Approve, issue (posts receivables) and void client invoices.",
    ),
    PermissionDef("payments.record", "Record client payments", "finance"),
    PermissionDef(
        "payments.approve",
        "Verify client payments",
        "finance",
        "Verify or reject recorded payments; verification posts to the bank.",
    ),
    PermissionDef("credit_notes.manage", "Manage credit notes and refunds", "finance"),
    PermissionDef("vendors.manage", "Manage vendors", "finance"),
    PermissionDef("bills.manage", "Manage vendor bills", "finance"),
    PermissionDef("expenses.manage", "Manage expenses", "finance"),
    PermissionDef("vendor_payments.manage", "Pay vendors", "finance"),
    PermissionDef("documents.client.view", "View client documents", "finance"),
    PermissionDef("documents.vendor.view", "View vendor documents", "finance"),
    PermissionDef(
        "documents.manage",
        "Upload and archive documents",
        "finance",
        "Bank payment proofs additionally require banking evidence access.",
    ),
    PermissionDef("banking.evidence.view", "View banking evidence", "finance"),
    PermissionDef("reports.export", "Export financial reports", "finance"),
    # Founder finance
    PermissionDef("founder.view", "View founder finance", "founder"),
    PermissionDef("founder.transactions.manage", "Manage founder transactions", "founder"),
    PermissionDef("founder.settlements.manage", "Manage founder settlements", "founder"),
    PermissionDef("ownership.manage", "Manage ownership records", "founder"),
    PermissionDef("founder.verify", "Verify founder corporate transactions", "founder"),
    PermissionDef(
        "founder.liabilities.manage",
        "Manage founder liabilities and recovery resolutions",
        "founder",
    ),
    PermissionDef("founder.personal.view", "View personal expense sharing", "founder"),
    PermissionDef("founder.personal.confirm", "Confirm own personal settlements", "founder"),
    PermissionDef(
        "founder.attest", "Record evidence-backed external participant attestations", "founder"
    ),
    PermissionDef(
        "founder.planning.manage", "Manage sharing policies and funding plans", "founder"
    ),
    PermissionDef("ownership.view", "View ownership agreements and register", "founder"),
    PermissionDef("ownership.approve", "Independently approve ownership changes", "founder"),
    PermissionDef("ownership.consent", "Authorize own ownership changes", "founder"),
    PermissionDef("ownership.attest", "Record external shareholder authorization", "founder"),
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


_FINANCE_MANAGER = {p.code for p in PERMISSIONS if p.category in {"administration", "finance"}} - {
    "accounting.approve",
    "accounting.periods.manage",
    "users.manage",
    "roles.manage",
    "permissions.manage",
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
                "sales.manage",
                "invoices.create",
                "payments.record",
                "vendors.manage",
                "bills.manage",
                "expenses.manage",
                "documents.client.view",
                "documents.vendor.view",
                "documents.manage",
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
