/** Shared, mutable state behind the global next/navigation mock (tests/setup.ts). */
export const nav = {
  pathname: '/dashboard',
  search: '',
  replace: vi.fn(),
  push: vi.fn(),
  refresh: vi.fn(),
};

export function resetNav(pathname = '/dashboard', search = '') {
  nav.pathname = pathname;
  nav.search = search;
  nav.replace.mockReset();
  nav.push.mockReset();
  nav.refresh.mockReset();
}
