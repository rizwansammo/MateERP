'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

import { CompactMark, Wordmark } from '@/components/brand/Wordmark';
import { Icon } from '@/components/ui/Icon';
import { useAuth } from '@/lib/auth/AuthProvider';
import { cn } from '@/lib/cn';
import { useSidebarMode } from '@/lib/preferences';

import { CompanyCard } from './CompanyCard';
import { SidebarNav } from './SidebarNav';

interface SidebarProps {
  /** Off-canvas drawer state below the 1000px breakpoint. */
  open: boolean;
  onNavigate: () => void;
}

export function Sidebar({ open, onNavigate }: SidebarProps) {
  const pathname = usePathname();
  const { mode, toggle } = useSidebarMode();
  const { savePreferences } = useAuth();
  const collapseLabel = mode === 'compact' ? 'Expand sidebar' : 'Collapse sidebar';

  return (
    <aside
      data-testid="sidebar"
      data-open={open}
      aria-label="Sidebar"
      className={cn(
        'fixed inset-y-0 left-0 z-40 flex h-screen w-[264px] flex-none flex-col border-r border-sb-bd bg-sb text-sb-tx',
        'max-md:-translate-x-full max-md:data-[open=true]:translate-x-0',
        'md:relative compact:w-16',
      )}
      style={{ transition: 'transform .2s ease, width .18s ease' }}
    >
      <Link
        href="/dashboard"
        onClick={onNavigate}
        aria-label="MateERP home"
        className="flex h-[60px] flex-none items-center border-b border-sb-bd px-[18px] hover:no-underline compact:justify-center"
      >
        <span className="flex items-center text-[23px] text-splash-fg compact:hidden">
          <Wordmark />
        </span>
        <span className="hidden compact:flex">
          <CompactMark />
        </span>
      </Link>

      <CompanyCard />

      <SidebarNavState key={pathname} pathname={pathname} onNavigate={onNavigate} />

      <div className="flex flex-none items-center justify-between gap-2 border-t border-sb-bd px-3 py-2.5 compact:justify-center">
        <div className="flex min-w-0 flex-col compact:hidden">
          <span className="text-[10.5px] text-sb-tx2">MateERP 0.6.0</span>
          <span className="text-[10px] text-sb-faint">Phase 6 · Operations & reporting</span>
        </div>
        <button
          type="button"
          onClick={() => {
            toggle();
            savePreferences({ sidebar: mode === 'compact' ? 'full' : 'compact' });
          }}
          aria-label={collapseLabel}
          title={collapseLabel}
          data-testid="sidebar-toggle"
          className="flex size-[30px] flex-none items-center justify-center border border-sb-bd bg-transparent text-sb-tx2 hover:bg-sb-h hover:text-white max-md:hidden"
        >
          <Icon name="left_panel_close" size={18} className="compact:hidden" />
          <Icon name="left_panel_open" size={18} className="hidden compact:inline" />
        </button>
      </div>
    </aside>
  );
}

/**
 * Keyed by pathname so manually opened/closed groups reset to "active group
 * open" after each navigation, matching the prototype.
 */
function SidebarNavState({ pathname, onNavigate }: { pathname: string; onNavigate: () => void }) {
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  return (
    <SidebarNav
      pathname={pathname}
      openOverrides={overrides}
      onToggle={(id, next) => setOverrides((prev) => ({ ...prev, [id]: next }))}
      onNavigate={onNavigate}
    />
  );
}
