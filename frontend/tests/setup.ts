import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

import { resetQueries } from '@/lib/api/query';

import { nav, resetNav } from './unit/navigation-mock';

vi.mock('next/navigation', () => ({
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ replace: nav.replace, push: nav.push, refresh: nav.refresh, back: vi.fn(), prefetch: vi.fn() }),
}));

// jsdom has no matchMedia; report a desktop-width viewport.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: /min-width:\s*1000px/.test(query),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

afterEach(() => {
  cleanup();
  resetQueries();
  resetNav();
  localStorage.clear();
  document.cookie = 'mateerp_csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  document.documentElement.dataset.theme = 'light';
  document.documentElement.dataset.sidebar = 'full';
});
