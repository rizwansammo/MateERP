import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Header } from '@/components/shell/Header';
import { Sidebar } from '@/components/shell/Sidebar';
import {
  PREFERENCES_BOOTSTRAP_SCRIPT,
  SIDEBAR_STORAGE_KEY,
  THEME_STORAGE_KEY,
} from '@/lib/preferences';

let mockPathname = '/sales/invoices';
vi.mock('next/navigation', () => ({ usePathname: () => mockPathname }));

const html = document.documentElement;

describe('theme switching', () => {
  it('toggles data-theme and persists the choice', async () => {
    render(<Header onOpenNavigation={() => {}} />);

    await userEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }));
    expect(html.dataset.theme).toBe('dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

    await userEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }));
    expect(html.dataset.theme).toBe('light');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('marks unbuilt header features as unavailable instead of faking them', () => {
    render(<Header onOpenNavigation={() => {}} />);
    for (const name of [/search/i, /^new/i, /notifications/i, /account/i]) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
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
    mockPathname = '/sales/invoices';
  });

  it('collapses to compact and expands again, persisting the mode', async () => {
    render(<Sidebar open={false} onNavigate={() => {}} />);

    await userEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(html.dataset.sidebar).toBe('compact');
    expect(localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('compact');

    await userEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }));
    expect(html.dataset.sidebar).toBe('full');
    expect(localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('full');
  });

  it('marks the active module and section', () => {
    render(<Sidebar open={false} onNavigate={() => {}} />);
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });

    const moduleLink = within(nav).getByRole('link', { name: /sales & billing/i });
    expect(moduleLink).toHaveAttribute('aria-current', 'page');
    expect(moduleLink).toHaveAttribute('aria-expanded', 'true');
    expect(within(nav).getByRole('link', { name: 'Invoices' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Create Invoice' })).not.toHaveAttribute('aria-current');
    expect(within(nav).getByRole('link', { name: /purchases/i })).not.toHaveAttribute('aria-current');
  });

  it('folds the active module sub-menu when its row is clicked', async () => {
    render(<Sidebar open={false} onNavigate={() => {}} />);
    const moduleLink = screen.getByRole('link', { name: /sales & billing/i });

    await userEvent.click(moduleLink);
    expect(moduleLink).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('link', { name: 'Invoices' })).not.toBeInTheDocument();

    await userEvent.click(moduleLink);
    expect(moduleLink).toHaveAttribute('aria-expanded', 'true');
  });

  it('keeps module names accessible in compact mode', async () => {
    render(<Sidebar open={false} onNavigate={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(screen.getByRole('link', { name: /banking & accounting/i })).toBeInTheDocument();
  });
});
