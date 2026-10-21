"""Stable report identities. Existing owning workflows remain the source of truth."""

from dataclasses import asdict, dataclass

from apps.accounts.authorization import get_permission_codes


@dataclass(frozen=True)
class Report:
    key: str
    title: str
    group: str
    description: str
    route: str
    permissions: tuple[str, ...] = ("finance.view",)


REPORTS = (
    Report(
        "pnl",
        "Profit & Loss",
        "financial",
        "Recognized posted income and expenses.",
        "/banking/statements/pnl",
    ),
    Report(
        "bs",
        "Balance Sheet",
        "financial",
        "Assets, liabilities and equity at the selected date.",
        "/banking/statements/bs",
    ),
    Report(
        "cf",
        "Cash Flow",
        "financial",
        "Operating, investing, financing and disclosed unclassified movements.",
        "/reports/cash-flow",
    ),
    Report(
        "tb",
        "Trial Balance",
        "financial",
        "Exact debit/credit balances with hierarchy subtotals.",
        "/banking/statements/tb",
    ),
    Report(
        "ledger",
        "General Ledger",
        "financial",
        "Source journals and running balances.",
        "/banking/ledger",
    ),
    Report(
        "income",
        "Income by Account",
        "financial",
        "Posted revenue, net of reversals and corrections.",
        "/reports/income",
    ),
    Report(
        "expense",
        "Expenses by Account",
        "financial",
        "Posted operating costs and cost of sales.",
        "/reports/expense",
    ),
    Report(
        "tax",
        "Tax Summary",
        "financial",
        "Recoverable input and output tax positions.",
        "/reports/tax",
    ),
    Report(
        "ar",
        "Receivables Aging",
        "financial",
        "Dated GL control allocations and due-date buckets.",
        "/reports/ar",
    ),
    Report(
        "ap",
        "Payables Aging",
        "financial",
        "Dated supplier obligations and settled allocations.",
        "/reports/ap",
    ),
    Report(
        "bank",
        "Bank Transaction Summary",
        "financial",
        "Actual cash movements and source drilldown.",
        "/reports/bank",
    ),
    Report(
        "customer",
        "Invoicing by Customer",
        "sales",
        "Issued invoicing, separately labelled from recognition and collections.",
        "/reports/customer",
    ),
    Report(
        "product",
        "Invoicing by Product / Service",
        "sales",
        "Frozen invoice lines; no current-price substitution.",
        "/reports/product",
    ),
    Report(
        "trends",
        "Invoicing & Collection Trends",
        "sales",
        "Posted receivables and verified collections.",
        "/sales/overview",
    ),
    Report(
        "projects",
        "Project Financial Performance",
        "sales",
        "Posted revenue and costs across historical currencies.",
        "/sales/projects",
    ),
    Report(
        "recurring",
        "Recurring Revenue Analysis",
        "sales",
        "Contract run rate, invoicing and collections remain distinct.",
        "/reports/recurring",
    ),
    Report(
        "orders",
        "Sales Order Performance",
        "sales",
        "Actual order and invoicing lifecycle.",
        "/sales/orders",
    ),
    Report(
        "credits",
        "Credits & Refunds",
        "sales",
        "Issued credits remain separate from actual cash refunds.",
        "/sales/credits",
    ),
    Report(
        "founder-contributions",
        "Founder Contributions",
        "founder",
        "Verified corporate funding; no promises or personal transfers.",
        "/founder/contributions",
        ("founder.view",),
    ),
    Report(
        "founder-expenses",
        "Founder-Paid Expenses",
        "founder",
        "Posted corporate costs and preserved founder obligations.",
        "/founder/expenses",
        ("founder.view",),
    ),
    Report(
        "founder-sharing",
        "Shared Expenses",
        "founder",
        "Frozen personal expense allocations.",
        "/founder/sharing",
        ("founder.view", "founder.personal.view"),
    ),
    Report(
        "founder-settlements",
        "Personal Settlements",
        "founder",
        "Personal balances stay outside company P&L and liabilities.",
        "/founder/settlements",
        ("founder.personal.view",),
    ),
    Report(
        "founder-loans",
        "Founder Loans",
        "founder",
        "Documented company loan obligations and repayments.",
        "/founder/loans",
        ("founder.view",),
    ),
    Report(
        "founder-reimbursements",
        "Company Reimbursements",
        "founder",
        "Actual verified recovery with overlap protection.",
        "/founder/reimbursements",
        ("founder.view",),
    ),
    Report(
        "founder-plans",
        "Funding Plan Summaries",
        "founder",
        "Immutable forecasts, never posted actual spending.",
        "/founder/sharing?tab=monthly",
        ("founder.view", "founder.planning.manage"),
    ),
    Report(
        "stock",
        "Inventory Valuation",
        "operational",
        "Immutable weighted-average quantity and cost events.",
        "/inventory/valuation",
    ),
    Report(
        "movements",
        "Stock Movements",
        "operational",
        "Receipts, issues, returns, counts and transfers.",
        "/inventory/movements",
    ),
    Report(
        "locations",
        "Stock by Location",
        "operational",
        "Company-owned quantities by warehouse or transit location.",
        "/reports/locations",
    ),
    Report(
        "low-stock",
        "Low Stock",
        "operational",
        "Tracked product balances against configured reorder levels.",
        "/reports/low-stock",
    ),
    Report(
        "purchases",
        "Purchase Order History",
        "operational",
        "Approved commitments do not inflate payables.",
        "/purchases/orders",
    ),
    Report(
        "receiving",
        "Goods Receipt History",
        "operational",
        "Accepted goods, historical costs and GRNI matching.",
        "/reports/receiving",
    ),
    Report(
        "vendors",
        "Vendor / Purchase Analysis",
        "operational",
        "Posted purchasing sources and supplier identity.",
        "/reports/vendors",
    ),
    Report(
        "assets",
        "Fixed Asset Summary",
        "operational",
        "Source-linked historical costs and actual carrying values.",
        "/assets/register",
    ),
    Report(
        "depreciation",
        "Posted Depreciation",
        "operational",
        "Planned estimates remain separate from posted service charges.",
        "/assets/depreciation",
    ),
    Report(
        "disposals",
        "Asset Disposals",
        "operational",
        "Retained asset removal, receivables and gains/losses.",
        "/assets/disposal",
    ),
    Report(
        "budgets",
        "Budget Variance",
        "operational",
        "Original/revised approved budgets and posted actuals.",
        "/budgets/comparison",
    ),
    Report(
        "cost-centers",
        "Cost Center Performance",
        "operational",
        "Audited analytical assignments with source drilldown.",
        "/budgets/costcenters",
    ),
    Report(
        "history",
        "Historical Onboarding Provenance",
        "financial",
        "Reconstructed activity and opening-only balances remain distinct.",
        "/reports/history",
        ("finance.view", "onboarding.manage"),
    ),
)
BY_KEY = {report.key: report for report in REPORTS}


def visible(user):
    codes = get_permission_codes(user)
    return [asdict(report) for report in REPORTS if set(report.permissions) <= codes]
