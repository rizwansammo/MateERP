'use client';

import { usePathname } from 'next/navigation';
import { type ReactNode, useEffect, useRef, useState } from 'react';

import { Header } from './Header';
import { Sidebar } from './Sidebar';

/** Application frame: sidebar, header and the scrolling main region. */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const mainRef = useRef<HTMLElement>(null);
  const [navOpen, setNavOpen] = useState(false);

  // Main is the scroll container, so reset it on navigation.
  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 });
  }, [pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNavOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [navOpen]);

  return (
    <div className="flex h-screen overflow-hidden bg-bg text-[13px] text-tx">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[200] focus:bg-sf focus:px-3 focus:py-2"
      >
        Skip to content
      </a>

      {navOpen && (
        <div
          data-testid="nav-scrim"
          aria-hidden="true"
          onClick={() => setNavOpen(false)}
          className="fixed inset-0 z-[39] bg-[rgba(3,7,12,.5)] md:hidden"
        />
      )}

      <Sidebar open={navOpen} onNavigate={() => setNavOpen(false)} />

      <div className="flex h-screen min-w-0 flex-1 flex-col">
        <Header onOpenNavigation={() => setNavOpen(true)} />
        <main id="main" ref={mainRef} className="relative min-h-0 flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
