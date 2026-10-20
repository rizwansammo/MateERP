import { buildCrumbs } from '@/components/shell/Breadcrumbs';
import { NAVIGATION, findNavItem, itemHref, resolveRoute } from '@/lib/navigation';

describe('resolveRoute', () => {
  it('maps a bare module path to its first section', () => {
    const route = resolveRoute('/sales');
    expect(route?.item.id).toBe('sales');
    expect(route?.sub?.slug).toBe('overview');
  });

  it('prefers the most specific section', () => {
    expect(resolveRoute('/sales/invoices/new')?.sub?.slug).toBe('invoices/new');
    expect(resolveRoute('/sales/invoices')?.sub?.slug).toBe('invoices');
  });

  it('keeps segments below a section as rest', () => {
    const route = resolveRoute('/sales/invoices/INV-0001');
    expect(route?.sub?.slug).toBe('invoices');
    expect(route?.rest).toEqual(['INV-0001']);
  });

  it('handles modules without sections', () => {
    const route = resolveRoute('/vendor-documents');
    expect(route?.item.id).toBe('vendor-documents');
    expect(route?.sub).toBeNull();
  });

  it('rejects unknown modules and sections', () => {
    expect(resolveRoute('/')).toBeNull();
    expect(resolveRoute('/payroll')).toBeNull();
    expect(resolveRoute('/sales/not-a-section')).toBeNull();
  });
});

describe('navigation tree', () => {
  it('has unique module ids and valid roadmap phases', () => {
    const items = NAVIGATION.flatMap((g) => g.items);
    expect(new Set(items.map((i) => i.id)).size).toBe(items.length);
    items.forEach((item) => {
      expect(item.phase).toBeGreaterThanOrEqual(2);
      expect(item.phase).toBeLessThanOrEqual(7);
    });
  });

  it('excludes HR and payroll, which belong to MateHR', () => {
    const labels = NAVIGATION.flatMap((g) => g.items.map((i) => i.label.toLowerCase()));
    expect(labels.some((l) => l.includes('payroll') || l.includes('hr'))).toBe(false);
  });

  it('links modules to their first section', () => {
    expect(itemHref(findNavItem('banking'))).toBe('/banking/overview');
    expect(itemHref(findNavItem('reports'))).toBe('/reports');
  });
});

describe('buildCrumbs', () => {
  it('builds Home › Group › Module › Section', () => {
    expect(buildCrumbs('/banking/journals').map((c) => c.label)).toEqual([
      'Home',
      'Finance',
      'Banking & Accounting',
      'Journal Entries',
    ]);
  });

  it('falls back to Home for unknown paths', () => {
    expect(buildCrumbs('/nope')).toEqual([{ label: 'Home', href: '/dashboard' }]);
  });
});
