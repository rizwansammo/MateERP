/*
 * Application navigation. Structure, labels and icons follow the approved
 * MateERP-UI prototype. `phase` is the roadmap phase that delivers the module;
 * modules above CURRENT_PHASE are shown as planned, never as working features.
 */

export const CURRENT_PHASE = 1;

export const PHASES: Record<number, string> = {
  1: 'Project Foundation',
  2: 'Authentication and Administration',
  3: 'Core Accounting Engine',
  4: 'Billing, Expenses and Documents',
  5: 'Founder Finance and Ownership',
  6: 'Business Operations and Reporting',
  7: 'Security, Final Testing and Release',
};

export interface NavSub {
  slug: string;
  label: string;
}

export interface NavItem {
  id: string;
  label: string;
  icon: string;
  phase: number;
  summary: string;
  subs?: NavSub[];
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

const sub = (slug: string, label: string): NavSub => ({ slug, label });

export const NAVIGATION: NavGroup[] = [
  {
    label: 'Overview',
    items: [
      {
        id: 'dashboard',
        label: 'Dashboard',
        icon: 'space_dashboard',
        phase: 6,
        summary: 'Executive financial KPIs, cash flow, receivables, payables and alerts.',
      },
    ],
  },
  {
    label: 'Finance',
    items: [
      {
        id: 'sales',
        label: 'Sales & Billing',
        icon: 'request_quote',
        phase: 4,
        summary:
          'Customers, sales orders, invoices, payments, official money receipts, recurring billing and credit notes.',
        subs: [
          sub('overview', 'Overview'),
          sub('customers', 'Customers'),
          sub('orders', 'Sales Orders'),
          sub('invoices', 'Invoices'),
          sub('invoices/new', 'Create Invoice'),
          sub('payments', 'Payments'),
          sub('receipts', 'Money Receipts'),
          sub('recurring', 'Recurring Billing'),
          sub('credits', 'Credit Notes & Refunds'),
          sub('projects', 'Project Financials'),
        ],
      },
      {
        id: 'purchases',
        label: 'Purchases & Expenses',
        icon: 'shopping_bag',
        phase: 4,
        summary:
          'Vendors, vendor bills, operating and recurring expenses, purchase orders and accounts payable.',
        subs: [
          sub('overview', 'Overview'),
          sub('expenses', 'Expenses'),
          sub('recurring', 'Recurring Expenses'),
          sub('vendors', 'Vendors & Suppliers'),
          sub('orders', 'Purchase Orders'),
          sub('bills', 'Vendor Bills'),
          sub('history', 'Purchase History'),
        ],
      },
      {
        id: 'banking',
        label: 'Banking & Accounting',
        icon: 'account_balance',
        phase: 3,
        summary:
          'Chart of accounts, double-entry journals, general ledger, bank reconciliation, periods and taxes.',
        subs: [
          sub('overview', 'Overview'),
          sub('accounts', 'Bank & Cash Accounts'),
          sub('transactions', 'Transactions'),
          sub('reconciliation', 'Reconciliation'),
          sub('coa', 'Chart of Accounts'),
          sub('ledger', 'General Ledger'),
          sub('journals', 'Journal Entries'),
          sub('periods', 'Accounting Periods'),
          sub('tax', 'Tax Management'),
          sub('statements', 'Financial Statements'),
        ],
      },
      {
        id: 'founder',
        label: 'Founder Finance',
        icon: 'handshake',
        phase: 5,
        summary:
          'Capital contributions, founder-paid expenses, sharing policies, settlements, loans and reimbursements.',
        subs: [
          sub('overview', 'Overview'),
          sub('contributions', 'Contributions'),
          sub('expenses', 'Founder Paid Expenses'),
          sub('sharing', 'Expense Sharing'),
          sub('settlements', 'Settlements'),
          sub('loans', 'Founder Loans'),
          sub('reimbursements', 'Company Reimbursements'),
          sub('statements', 'Founder Statements'),
        ],
      },
      {
        id: 'ownership',
        label: 'Ownership & Capital',
        icon: 'donut_large',
        phase: 5,
        summary: 'Shareholders, ownership percentages, capital records, transfers and issuance.',
        subs: [
          sub('shareholders', 'Shareholders'),
          sub('overview', 'Ownership Overview'),
          sub('capital', 'Capital Records'),
          sub('transfers', 'Share Transfers'),
          sub('issuance', 'Share Issuance'),
          sub('history', 'Ownership History'),
        ],
      },
      {
        id: 'budgets',
        label: 'Budgets & Costs',
        icon: 'savings',
        phase: 6,
        summary: 'Budgets, cost centers and budget-versus-actual comparisons.',
        subs: [
          sub('budgets', 'Budgets'),
          sub('costcenters', 'Cost Centers'),
          sub('comparison', 'Budget Comparisons'),
        ],
      },
    ],
  },
  {
    label: 'Operations',
    items: [
      {
        id: 'inventory',
        label: 'Inventory & Warehouse',
        icon: 'inventory_2',
        phase: 6,
        summary: 'Items, stock movements, warehouse locations, transfers and valuation.',
        subs: [
          sub('overview', 'Inventory Overview'),
          sub('items', 'Items & Stock'),
          sub('movements', 'Stock Movements'),
          sub('locations', 'Stock Locations'),
          sub('transfers', 'Transfers'),
          sub('valuation', 'Stock Valuation'),
        ],
      },
      {
        id: 'assets',
        label: 'Fixed Assets',
        icon: 'devices',
        phase: 6,
        summary: 'Asset register, depreciation and disposal.',
        subs: [
          sub('register', 'Asset Register'),
          sub('details', 'Asset Details'),
          sub('depreciation', 'Depreciation'),
          sub('disposal', 'Asset Disposal'),
        ],
      },
      {
        id: 'catalog',
        label: 'Products & Services',
        icon: 'category',
        phase: 6,
        summary: 'Product and service catalog with pricing.',
        subs: [
          sub('products', 'Product Catalog'),
          sub('services', 'Service Catalog'),
          sub('pricing', 'Pricing'),
        ],
      },
    ],
  },
  {
    label: 'Documents',
    items: [
      {
        id: 'vendor-documents',
        label: 'Vendor Documents',
        icon: 'folder_open',
        phase: 4,
        summary: 'Vendor invoices and payment receipts organised by Year → Month → Vendor.',
      },
      {
        id: 'client-documents',
        label: 'Client Documents',
        icon: 'folder_shared',
        phase: 4,
        summary:
          'Client invoices, money receipts and bank payment proofs organised by Year → Client → Invoice.',
      },
    ],
  },
  {
    label: 'Management',
    items: [
      {
        id: 'reports',
        label: 'Reports & Analytics',
        icon: 'monitoring',
        phase: 6,
        summary: 'Financial statements, analytics and exports.',
      },
      {
        id: 'settings',
        label: 'Settings & Administration',
        icon: 'settings',
        phase: 2,
        summary:
          'Company profile, invoice branding, users, roles, permissions, approvals and audit logs.',
        subs: [
          sub('company', 'Company Profile'),
          sub('branding', 'Invoice & Receipt Branding'),
          sub('users', 'Users & Roles'),
          sub('permissions', 'Permissions'),
          sub('approvals', 'Approvals'),
          sub('modules', 'Modules'),
          sub('financial', 'Financial Settings'),
          sub('currency', 'Currency Settings'),
          sub('tax', 'Tax Settings'),
          sub('notifications', 'Notification Preferences'),
          sub('audit', 'Audit Logs'),
          sub('integrations', 'Integration Settings'),
          sub('preferences', 'Application Preferences'),
          sub('about', 'About MateERP'),
        ],
      },
    ],
  },
];

export interface ResolvedRoute {
  group: NavGroup;
  item: NavItem;
  sub: NavSub | null;
  /** Path segments after the matched sub-section. */
  rest: string[];
}

export function findNavItem(id: string): NavItem {
  for (const group of NAVIGATION) {
    const item = group.items.find((candidate) => candidate.id === id);
    if (item) return item;
  }
  throw new Error(`Unknown navigation item: ${id}`);
}

export function itemHref(item: NavItem): string {
  const first = item.subs?.[0];
  return first ? `/${item.id}/${first.slug}` : `/${item.id}`;
}

export function subHref(item: NavItem, s: NavSub): string {
  return `/${item.id}/${s.slug}`;
}

/** Map a pathname onto the navigation tree. Returns null for unknown modules. */
export function resolveRoute(pathname: string): ResolvedRoute | null {
  const segments = pathname.split('/').filter(Boolean).map(decodeURIComponent);
  const [moduleId, ...rest] = segments;
  if (!moduleId) return null;

  for (const group of NAVIGATION) {
    const item = group.items.find((candidate) => candidate.id === moduleId);
    if (!item) continue;
    if (!item.subs?.length) return { group, item, sub: null, rest };

    const restPath = rest.join('/');
    // Longest slug wins, so "invoices/new" beats "invoices".
    const match = [...item.subs]
      .sort((a, b) => b.slug.length - a.slug.length)
      .find((s) => restPath === s.slug || restPath.startsWith(`${s.slug}/`));
    if (match) {
      return { group, item, sub: match, rest: rest.slice(match.slug.split('/').length) };
    }
    if (rest.length === 0) return { group, item, sub: item.subs[0] ?? null, rest: [] };
    return null;
  }
  return null;
}
