import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AuditPage } from '@/features/settings/audit/AuditPage';
import { CompanyDrawer } from '@/features/settings/company/CompanyDrawer';
import { ModulesPage } from '@/features/settings/modules/ModulesPage';
import { PermissionsPage, diffCount } from '@/features/settings/permissions/PermissionMatrix';
import { UsersPage } from '@/features/settings/users/UsersPage';
import type { CompanyProfile, Role } from '@/lib/api/types';

import { makeUser, mockApi, renderWithAuth, viewerUser } from './helpers';

const page = <T,>(results: T[]) => ({ count: results.length, page: 1, page_size: 25, total_pages: 1, results });

const ROLES: Role[] = [
  { id: 1, key: 'administrator', name: 'Administrator', description: '', is_system: true, is_admin: true, is_active: true, permissions: ['audit.view', 'finance.view'], user_count: 1 },
  { id: 5, key: 'viewer', name: 'Viewer', description: '', is_system: true, is_admin: false, is_active: true, permissions: ['finance.view'], user_count: 0 },
];
const CATALOG = [
  { code: 'audit.view', label: 'View audit logs', category: 'administration', category_label: 'Administration', description: '' },
  { code: 'finance.view', label: 'View financial records', category: 'finance', category_label: 'Finance', description: '' },
];

describe('permission matrix', () => {
  it('counts pending changes', () => {
    expect(diffCount(ROLES, { 5: new Set(['finance.view', 'audit.view']) })).toBe(1);
    expect(diffCount(ROLES, { 5: new Set() })).toBe(1);
    expect(diffCount(ROLES, {})).toBe(0);
  });

  it('stages toggles, keeps Administrator locked and saves atomically', async () => {
    const calls = mockApi({
      '/auth/me/': makeUser(),
      '/roles/': ROLES,
      '/permissions/': CATALOG,
      'POST /roles/permissions/': ROLES.map((r) => (r.id === 5 ? { ...r, permissions: ['audit.view', 'finance.view'] } : r)),
    });
    renderWithAuth(<PermissionsPage />);
    const cell = await screen.findByRole('switch', { name: 'View audit logs for Viewer' });
    expect(screen.getByRole('switch', { name: 'View audit logs for Administrator' })).toBeDisabled();

    await userEvent.click(cell);
    expect(cell).toHaveAttribute('aria-checked', 'true');
    const bar = screen.getByRole('region', { name: 'Unsaved permission changes' });
    expect(bar).toHaveTextContent('1 unsaved change');
    await userEvent.click(within(bar).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Unsaved permission changes' })).not.toBeInTheDocument());
    const save = calls.find((c) => c.path === '/roles/permissions/')!;
    expect(save.body).toEqual({ changes: { '5': ['finance.view', 'audit.view'] } });
  });
});

describe('company drawer', () => {
  const company = { display_name: 'NetaMate', legal_name: '', email: '', phone: '', website: '', address_line1: '', address_line2: '', city: '', region: '', postal_code: '', country: '', tax_id: '', registration_number: '', base_currency: 'BDT', time_zone: 'Asia/Dhaka', fiscal_year_start_month: 1, notes: '', logo: null, created_at: '', updated_at: '' } satisfies CompanyProfile;

  it('only saves when dirty and shows server field errors', async () => {
    const calls = mockApi({
      '/auth/me/': makeUser(),
      '/reference/currencies/': [{ code: 'BDT', name: 'Bangladeshi Taka', symbol: '৳', minor_units: 2 }],
      '/reference/timezones/': [{ name: 'Asia/Dhaka' }],
      'PUT /company/': [400, { error: { code: 'validation_error', message: 'The request contains invalid data.', details: { website: ['Enter a valid URL.'] }, request_id: null } }],
    });
    renderWithAuth(<CompanyDrawer company={company} onClose={() => {}} onSaved={() => {}} />);
    const save = screen.getByRole('button', { name: 'Save changes' });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Website'), 'not a url');
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(await screen.findByText('Enter a valid URL.')).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'PUT')!.body).toMatchObject({ website: 'not a url', display_name: 'NetaMate' });
  });
});

describe('modules page', () => {
  const modules = { optional: [{ key: 'inventory', label: 'Inventory & Warehouse', description: '', phase: 6, nav_id: 'inventory', enabled: true, implemented: false }], core: ['Core accounting'] };

  it('toggles optional modules and keeps planned status honest', async () => {
    const calls = mockApi({ '/auth/me/': makeUser(), '/modules/': modules, 'PUT /modules/inventory/': { ...modules.optional[0], enabled: false } });
    renderWithAuth(<ModulesPage />);
    expect(await screen.findByText('Planned · Phase 6')).toBeInTheDocument();
    expect(screen.getByText('Mandatory')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('switch', { name: 'Inventory & Warehouse module' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ enabled: false }));
  });

  it('is read-only without company.edit', async () => {
    mockApi({ '/auth/me/': viewerUser, '/modules/': modules });
    renderWithAuth(<ModulesPage />, viewerUser);
    expect(await screen.findByRole('switch', { name: 'Inventory & Warehouse module' })).toBeDisabled();
  });
});

describe('audit page', () => {
  it('requests server-side filters', async () => {
    const calls = mockApi({
      '/auth/me/': makeUser(),
      '/audit/facets/': { categories: ['auth', 'user'], actions: [] },
      '/audit/events/': page([{ id: 'e1', occurred_at: '2026-10-20T10:00:00Z', actor: 1, actor_label: 'admin', action: 'auth.login.failed', category: 'auth', target_type: '', target_id: '', target_label: 'unknown identifier', request_id: 'r', ip_address: null, before: null, after: null, outcome: 'failure', reason: '' }]),
    });
    renderWithAuth(<AuditPage />);
    expect(await screen.findByText('Sign-in failed')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('radio', { name: 'Auth' }));
    await userEvent.selectOptions(screen.getByLabelText('Outcome'), 'failure');
    await waitFor(() => expect(calls.some((c) => c.path.startsWith('/audit/events/') && c.path.includes('category=auth') && c.path.includes('outcome=failure'))).toBe(true));
  });

  it('is restricted without audit.view', () => {
    mockApi({ '/auth/me/': viewerUser });
    renderWithAuth(<AuditPage />, viewerUser);
    expect(screen.getByText('Access restricted')).toBeInTheDocument();
  });
});

describe('users page', () => {
  it('creates a user and shows the temporary password once', async () => {
    const created = { id: 9, username: 'bob', email: 'bob@example.test', first_name: 'Bob', last_name: '', display_name: 'Bob', initials: 'B', role: { id: 5, name: 'Viewer', is_admin: false }, is_active: true, must_change_password: true, last_login: null, date_joined: '2026-10-20T10:00:00Z' };
    const calls = mockApi({
      '/auth/me/': makeUser(),
      '/roles/': ROLES,
      'GET /users/': page([]),
      'POST /users/': [201, { user: created, temporary_password: 'Tmp-Abc123xyz9876' }],
    });
    renderWithAuth(<UsersPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Create user' }));
    await userEvent.type(screen.getByLabelText(/^Username/), 'bob');
    await userEvent.type(screen.getByLabelText(/^Email/), 'bob@example.test');
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Create user' }));
    expect(await screen.findByTestId('temporary-password')).toHaveTextContent('Tmp-Abc123xyz9876');
    expect(calls.find((c) => c.method === 'POST' && c.path === '/users/')!.body).toMatchObject({ username: 'bob', role: 5, is_active: true });
    await userEvent.click(screen.getByRole('button', { name: 'I have shared it securely' }));
    expect(screen.queryByTestId('temporary-password')).not.toBeInTheDocument();
  });
});
