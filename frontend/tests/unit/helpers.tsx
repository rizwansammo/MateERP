import { render } from '@testing-library/react';
import type { ReactElement } from 'react';

import type { CurrentUser } from '@/lib/api/types';
import { AuthProvider } from '@/lib/auth/AuthProvider';

export const ALL_PERMISSIONS = [
  'company.view', 'company.edit', 'branding.manage', 'users.manage', 'roles.manage', 'permissions.manage',
  'approvals.manage', 'audit.view', 'finance.view', 'accounting.manage', 'invoices.create', 'payments.approve',
  'expenses.manage', 'banking.evidence.view', 'reports.export', 'founder.view', 'founder.transactions.manage',
  'founder.settlements.manage', 'ownership.manage', 'procurement.manage', 'inventory.manage', 'assets.manage',
  'budgets.manage',
  'founder.verify', 'founder.liabilities.manage', 'founder.personal.view', 'founder.personal.confirm',
  'founder.attest', 'founder.planning.manage', 'ownership.view', 'ownership.approve', 'ownership.consent', 'ownership.attest',
  'accounting.approve', 'accounting.periods.manage',
  'sales.manage', 'invoices.issue', 'payments.record', 'credit_notes.manage', 'vendors.manage',
  'bills.manage', 'vendor_payments.manage', 'documents.client.view', 'documents.vendor.view', 'documents.manage',
  'catalog.manage', 'procurement.approve', 'inventory.post', 'assets.post', 'budgets.approve', 'onboarding.manage', 'fulfillment.manage', 'reports.classify',
];

export function makeUser(overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: 1,
    username: 'admin',
    email: 'admin@example.test',
    first_name: 'Ada',
    last_name: 'Admin',
    display_name: 'Ada Admin',
    initials: 'AA',
    role: { id: 1, name: 'Administrator', is_admin: true },
    permissions: ALL_PERMISSIONS,
    must_change_password: false,
    preferences: {},
    last_login: null,
    ...overrides,
  };
}

export const viewerUser = makeUser({
  id: 2,
  username: 'viv',
  display_name: 'Viv Viewer',
  initials: 'VV',
  role: { id: 5, name: 'Viewer', is_admin: false },
  permissions: ['finance.view'],
});

export interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

type Handler = unknown | ((call: Call) => unknown);

/**
 * Mock fetch by "METHOD /path/" (or "/path/" for any method). Values can be
 * a body, a function returning a body, or [status, body]. Unmatched requests
 * return 404. Returns the list of calls for assertions.
 */
export function mockApi(routes: Record<string, Handler>): Call[] {
  const calls: Call[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost');
    const method = (init?.method ?? 'GET').toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, '');
    const headers = Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>));
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body ?? null;
    const call = { method, path: `${path}${url.search}`, body, headers };
    calls.push(call);
    const handler = routes[`${method} ${path}`] ?? routes[path];
    if (handler === undefined) {
      if (path === '/auth/csrf/') {
        document.cookie = 'mateerp_csrftoken=test-token';
        return new Response(JSON.stringify({ csrf_token: 'test-token' }), { status: 200 });
      }
      return new Response(JSON.stringify({ error: { code: 'not_found', message: 'Not found', details: null, request_id: null } }), { status: 404 });
    }
    const value = typeof handler === 'function' ? (handler as (c: Call) => unknown)(call) : handler;
    const [status, payload] = Array.isArray(value) && typeof value[0] === 'number' && value.length === 2 ? (value as [number, unknown]) : [200, value];
    return new Response(status === 204 ? null : JSON.stringify(payload), { status });
  });
  return calls;
}

export function renderWithAuth(ui: ReactElement, user: CurrentUser = makeUser()) {
  return render(<AuthProvider initialUser={user}>{ui}</AuthProvider>);
}
