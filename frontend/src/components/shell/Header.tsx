'use client';

import { Icon } from '@/components/ui/Icon';
import { IconButton } from '@/components/ui/IconButton';
import { useTheme } from '@/lib/preferences';

import { Breadcrumbs } from './Breadcrumbs';

/*
 * Header controls whose features are not built yet are rendered for visual
 * fidelity but are disabled and say which phase delivers them. They never
 * pretend to work.
 */
const PLANNED = {
  search: 'Global search becomes available as business modules are delivered (Phase 4).',
  create: 'Quick-create actions arrive with the business modules (Phases 3–4).',
  notifications: 'Notifications arrive with approvals and business workflows (Phase 2+).',
  account: 'Sign-in and user accounts arrive in Phase 2.',
};

export function Header({ onOpenNavigation }: { onOpenNavigation: () => void }) {
  const { theme, toggleTheme } = useTheme();
  const themeLabel = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';

  return (
    <header className="relative z-30 flex h-14 flex-none items-center gap-3 border-b border-bd bg-hd px-[18px] leading-[normal] max-sm:gap-2 max-sm:px-3">
      <IconButton
        icon="menu"
        iconSize={20}
        label="Open navigation"
        onClick={onOpenNavigation}
        className="md:hidden"
      />

      <Breadcrumbs />

      <button
        type="button"
        disabled
        title={PLANNED.search}
        aria-label="Search (not yet available)"
        className="flex h-[34px] w-[34px] flex-none items-center gap-2 border border-bd bg-sf2 px-2.5 text-left text-[12.5px] text-tx3 lg:w-[340px] max-sm:hidden"
      >
        <Icon name="search" size={18} className="-ml-px" />
        <span className="hidden flex-1 lg:inline">Search records, documents, pages…</span>
        <span className="hidden border border-bd2 px-[5px] py-px font-mono text-[10.5px] font-medium lg:inline">
          Ctrl K
        </span>
      </button>

      <button
        type="button"
        disabled
        title={PLANNED.create}
        aria-label="New (not yet available)"
        className="flex h-[34px] flex-none items-center gap-[5px] border border-pr bg-pr px-3 text-[12.5px] font-semibold text-prt disabled:cursor-not-allowed max-lg:px-2"
      >
        <Icon name="add" size={18} />
        <span className="hidden lg:inline">New</span>
      </button>

      <IconButton
        icon="notifications"
        label="Notifications (not yet available)"
        title={PLANNED.notifications}
        disabled
        className="disabled:opacity-100"
      />

      <button
        type="button"
        onClick={toggleTheme}
        aria-label={themeLabel}
        title={themeLabel}
        data-testid="theme-toggle"
        className="flex size-[34px] flex-none items-center justify-center border border-bd bg-transparent text-tx hover:bg-sf3"
      >
        <Icon name="dark_mode" size={19} className="dark:hidden" />
        <Icon name="light_mode" size={19} className="hidden dark:inline" />
      </button>

      <button
        type="button"
        disabled
        title={PLANNED.account}
        aria-label="Account (sign-in arrives in Phase 2)"
        className="flex h-[34px] flex-none items-center gap-2 border border-bd bg-transparent pr-2 pl-1 text-tx disabled:cursor-not-allowed"
      >
        <span className="flex size-[26px] items-center justify-center bg-[var(--c2)] text-white">
          <Icon name="person" size={16} />
        </span>
        <span className="hidden flex-col items-start leading-[1.15] lg:flex">
          <span className="text-[12px] font-semibold">Not signed in</span>
          <span className="text-[10.5px] text-tx3">Accounts in Phase 2</span>
        </span>
        <Icon name="expand_more" size={16} className="text-tx3" />
      </button>
    </header>
  );
}
