import { screen, waitFor, within } from '@testing-library/react';

import { AuthProvider } from '@/lib/auth/AuthProvider';
import userEvent from '@testing-library/user-event';

import { Header } from '@/components/shell/Header';
import { Sidebar } from '@/components/shell/Sidebar';
import {
  PREFERENCES_BOOTSTRAP_SCRIPT,
  SIDEBAR_STORAGE_KEY,
  THEME_STORAGE_KEY,
} from '@/lib/preferences';

import { makeUser, mockApi, renderWithAuth, viewerUser } from './helpers';
import { nav } from './navigation-mock';

const html = document.documentElement;
const MODULES = {
  optional: ['founder', 'ownership', 'procurement', 'inventory', 'assets', 'budgeting'].map((key) => ({
    key, label: key, description: '', phase: 6, nav_id: key, enabled: key !== 'inventory', implemented: false,
  })),
  core: [],
};
const baseRoutes = {
  '/auth/me/': makeUser(),
  '/modules/': MODULES,
  '/company/summary/': { configured: true, display_name: 'NetaMate', legal_name: null, initials: 'N', location: 'Dhaka, Bangladesh', logo_url: null },
  '/approvals/requests/': { count: 0, page: 1, page_size: 25, total_pages: 1, results: [] },
};

describe('theme switching', () => {
  it('toggles data-theme, persists locally and saves to the account', async () => {
    const calls = mockApi({ ...baseRoutes, 'PATCH /auth/me/': makeUser({ preferences: { theme: 'dark' } }) });
    renderWithAuth(<Header onOpenNavigation={() => {}} />);

    await userEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }));
    expect(html.dataset.theme).toBe('dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH' && c.path === '/auth/me/')?.body).toEqual({ preferences: { theme: 'dark' } }),
    );
  });

  it('opens real search and quick-create controls', async () => {
    mockApi(baseRoutes);
    renderWithAuth(<Header onOpenNavigation={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: 'Search records and pages' }));
    expect(screen.getByRole('dialog', { name: 'Search MateERP' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Search pages and records' })).toHaveFocus();
    await userEvent.click(screen.getByRole('button', { name: 'Close search' }));
    expect(screen.queryByRole('dialog', { name: 'Search MateERP' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Create new record' }));
    expect(screen.getByRole('menu', { name: 'Create new record' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /notifications/i })).toBeEnabled();
  });
});

describe('account menu', () => {
  it('shows the signed-in user and signs out', async () => {
    const calls = mockApi({ ...baseRoutes, 'POST /auth/logout/': [204, null] });
    renderWithAuth(<Header onOpenNavigation={() => {}} />);

    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }));
    const menu = screen.getByRole('menu', { name: 'Account' });
    expect(within(menu).getByText('Ada Admin')).toBeInTheDocument();
    expect(within(menu).getByText('Administrator')).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: /change password/i })).toBeInTheDocument();

    await userEvent.click(within(menu).getByRole('menuitem', { name: /sign out/i }));
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/login'));
    expect(calls.some((c) => c.method === 'POST' && c.path === '/auth/logout/' && c.headers['X-CSRFToken'])).toBe(true);
  });

  it('lists approval requests waiting for the user', async () => {
    mockApi({
      ...baseRoutes,
      '/approvals/requests/': { count: 1, page: 1, page_size: 25, total_pages: 1, results: [{ id: 7, title: 'Publish invoice & receipt branding', requested_by: { id: 2, display_name: 'Rizwan' }, requested_at: '2026-10-20T10:00:00Z' }] },
    });
    renderWithAuth(<Header onOpenNavigation={() => {}} />);
    const bell = await screen.findByRole('button', { name: 'Notifications (1 pending approvals)' });
    await userEvent.click(bell);
    expect(screen.getByText('Publish invoice & receipt branding')).toBeInTheDocument();
  });
});

describe('preferences bootstrap script', () => {
  it('applies stored preferences before React loads', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    localStorage.setItem(SIDEBAR_STORAGE_KEY, 'compact');
    new Function(PREFERENCES_BOOTSTRAP_SCRIPT)();
    expect(html.dataset.theme).toBe('dark');
    expect(html.dataset.sidebar).toBe('compact');
  });

  it('ignores unexpected stored values', () => {
    localStorage.setItem(THEME_STORAGE_KEY, '"><script>');
    new Function(PREFERENCES_BOOTSTRAP_SCRIPT)();
    expect(html.dataset.theme).toBe('light');
  });
});

describe('sidebar', () => {
  beforeEach(() => {
    nav.pathname = '/sales/invoices';
  });

  it('collapses to compact and expands again, persisting the mode', async () => {
    mockApi({ ...baseRoutes, 'PATCH /auth/me/': makeUser() });
    renderWithAuth(<Sidebar open={false} onNavigate={() => {}} />);

    await userEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(html.dataset.sidebar).toBe('compact');
    expect(localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('compact');
    await userEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }));
    expect(html.dataset.sidebar).toBe('full');
  });

  it('keeps multiple modules open across route changes without jumping the sidebar', async () => {
    mockApi(baseRoutes);
    const onNavigate = vi.fn();
    const sidebar = <Sidebar open={false} onNavigate={onNavigate} />;
    const { rerender } = renderWithAuth(sidebar);

    const navigation = screen.getByRole('navigation', { name: 'Main navigation' });
    const sales = within(navigation).getByRole('link', { name: /sales & billing/i });
    const purchases = within(navigation).getByRole('link', { name: /purchases & expenses/i });
    const banking = within(navigation).getByRole('link', { name: /banking & accounting/i });

    expect(sales).toHaveAttribute('aria-expanded', 'true');
    expect(purchases).toHaveAttribute('aria-expanded', 'false');

    await userEvent.click(purchases);
    expect(sales).toHaveAttribute('aria-expanded', 'true');
    expect(purchases).toHaveAttribute('aria-expanded', 'true');

    navigation.scrollTop = 180;
    nav.pathname = '/purchases/vendors';
    rerender(<AuthProvider initialUser={makeUser()}>{sidebar}</AuthProvider>);
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBe(navigation);
    expect(navigation.scrollTop).toBe(180);
    expect(sales).toHaveAttribute('aria-expanded', 'true');
    expect(purchases).toHaveAttribute('aria-expanded', 'true');
    expect(within(navigation).getByRole('link', { name: 'Vendors & Suppliers' })).toHaveAttribute('aria-current', 'page');

    // Any expanded section can be collapsed without navigating away or closing the others.
    const navigationCount = onNavigate.mock.calls.length;
    await userEvent.click(sales);
    expect(sales).toHaveAttribute('aria-expanded', 'false');
    expect(purchases).toHaveAttribute('aria-expanded', 'true');
    expect(onNavigate).toHaveBeenCalledTimes(navigationCount);

    // Explicitly closed sections stay closed when revisiting them.
    nav.pathname = '/sales/invoices';
    rerender(<AuthProvider initialUser={makeUser()}>{sidebar}</AuthProvider>);
    expect(sales).toHaveAttribute('aria-expanded', 'false');
    expect(purchases).toHaveAttribute('aria-expanded', 'true');

    // A newly visited module opens without collapsing the other expanded modules.
    nav.pathname = '/banking/accounts';
    rerender(<AuthProvider initialUser={makeUser()}>{sidebar}</AuthProvider>);
    await waitFor(() => expect(banking).toHaveAttribute('aria-expanded', 'true'));
    expect(purchases).toHaveAttribute('aria-expanded', 'true');
    expect(sales).toHaveAttribute('aria-expanded', 'false');
  });

  it('uses the slightly larger sidebar wordmark and balanced ATE lettering', () => {
    mockApi(baseRoutes);
    renderWithAuth(<Sidebar open={false} onNavigate={() => {}} />);
    const home = screen.getByRole('link', { name: 'MateERP home' });
    const mark = within(home).getAllByRole('img', { name: 'MateERP' })[0]!;
    expect(mark.parentElement?.className).toContain('text-[26px]');
    expect(mark.children[1]?.className).toContain('text-[.82em]');
    expect(mark.children[2]?.className).toContain('text-brand');
  });

  it('marks the active module and section', () => {
    mockApi(baseRoutes);
    renderWithAuth(<Sidebar open={false} onNavigate={() => {}} />);
    const navEl = screen.getByRole('navigation', { name: 'Main navigation' });
    const moduleLink = within(navEl).getByRole('link', { name: /sales & billing/i });
    expect(moduleLink).toHaveAttribute('aria-current', 'page');
    expect(within(navEl).getByRole('link', { name: 'Invoices' })).toHaveAttribute('aria-current', 'page');
  });

  it('shows the real company and hides disabled optional modules', async () => {
    mockApi(baseRoutes);
    renderWithAuth(<Sidebar open={false} onNavigate={() => {}} />);
    expect(await screen.findByText('NetaMate')).toBeInTheDocument();
    expect(screen.getByText('Dhaka, Bangladesh')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('link', { name: /inventory & warehouse/i })).not.toBeInTheDocument());
    expect(screen.getByRole('link', { name: /fixed assets/i })).toBeInTheDocument();
  });

  it('marks modules outside the user’s role with a lock', () => {
    mockApi({ ...baseRoutes, '/auth/me/': viewerUser });
    renderWithAuth(<Sidebar open={false} onNavigate={() => {}} />, viewerUser);
    const founder = screen.getByRole('link', { name: /founder finance/i });
    expect(within(founder).getByText('lock')).toBeInTheDocument();
    expect(within(screen.getByRole('link', { name: /sales & billing/i })).queryByText('lock')).not.toBeInTheDocument();
  });
});
