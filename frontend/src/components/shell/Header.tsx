'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Icon } from '@/components/ui/Icon';
import { IconButton } from '@/components/ui/IconButton';
import { useApprovalInbox } from '@/lib/api/hooks';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDateTime } from '@/lib/format';
import { useTheme } from '@/lib/preferences';

import { Breadcrumbs } from './Breadcrumbs';

/*
 * Search and quick-create belong to the business modules and stay disabled
 * (with the delivering phase named) until those modules exist.
 */
const PLANNED = {
  search: 'Global cross-module search is planned. Use the search in each directory.',
  create: 'Quick-create actions arrive with the business modules (Phases 3–4).',
};

type Menu = 'account' | 'notifications' | null;

export function Header({ onOpenNavigation }: { onOpenNavigation: () => void }) {
  const { theme, toggleTheme } = useTheme();
  const { savePreferences } = useAuth();
  const [menu, setMenu] = useState<Menu>(null);
  const themeLabel = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';

  useEffect(() => {
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(null);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menu]);

  const toggle = (which: Exclude<Menu, null>) => setMenu((m) => (m === which ? null : which));

  return (
    <>
      <header className="relative z-30 flex h-14 flex-none items-center gap-3 border-b border-bd bg-hd px-[18px] leading-[normal] max-sm:gap-2 max-sm:px-3">
        <IconButton icon="menu" iconSize={20} label="Open navigation" onClick={onOpenNavigation} className="md:hidden" />

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
          <span className="hidden border border-bd2 px-[5px] py-px font-mono text-[10.5px] font-medium lg:inline">Ctrl K</span>
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

        <div className="relative">
          <NotificationsButton open={menu === 'notifications'} onToggle={() => toggle('notifications')} />
          {menu === 'notifications' && <NotificationsPanel onClose={() => setMenu(null)} />}
        </div>

        <button
          type="button"
          onClick={() => {
            toggleTheme();
            savePreferences({ theme: theme === 'dark' ? 'light' : 'dark' });
          }}
          aria-label={themeLabel}
          title={themeLabel}
          data-testid="theme-toggle"
          className="flex size-[34px] flex-none items-center justify-center border border-bd bg-transparent text-tx hover:bg-sf3"
        >
          <Icon name="dark_mode" size={19} className="dark:hidden" />
          <Icon name="light_mode" size={19} className="hidden dark:inline" />
        </button>

        <div className="relative">
          <AccountButton open={menu === 'account'} onToggle={() => toggle('account')} />
          {menu === 'account' && <AccountMenu onClose={() => setMenu(null)} />}
        </div>
      </header>
      {menu && (
        <div aria-hidden="true" className="fixed inset-x-0 top-14 bottom-0 z-[25]" onClick={() => setMenu(null)} />
      )}
    </>
  );
}

function AccountButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const { user } = useAuth();
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label="Account menu"
      aria-haspopup="menu"
      aria-expanded={open}
      className="flex h-[34px] flex-none items-center gap-2 border border-bd bg-transparent pr-2 pl-1 text-tx hover:bg-sf3"
    >
      <span className="flex size-[26px] items-center justify-center bg-[var(--c2)] text-[11px] font-semibold text-white">
        {user.initials}
      </span>
      <span className="hidden flex-col items-start leading-[1.15] lg:flex">
        <span className="max-w-[160px] truncate text-[12px] font-semibold">{user.display_name}</span>
        <span className="text-[10.5px] text-tx3">{user.role?.name ?? 'No role'}</span>
      </span>
      <Icon name="expand_more" size={16} className="text-tx3" />
    </button>
  );
}

function AccountMenu({ onClose }: { onClose: () => void }) {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const go = (href: string) => {
    onClose();
    router.push(href);
  };
  const links = [
    { icon: 'person', label: 'My profile', href: '/account/profile' },
    { icon: 'key', label: 'Change password', href: '/account/password' },
    { icon: 'tune', label: 'Application preferences', href: '/settings/preferences' },
    { icon: 'info', label: 'About MateERP', href: '/settings/about' },
  ];
  const row =
    'flex w-full items-center gap-2.5 bg-transparent px-3.5 py-2 text-left text-[12.5px] font-medium text-tx hover:bg-sf3';
  return (
    <div role="menu" aria-label="Account" className="absolute top-10 right-0 z-50 w-[290px] animate-rise border border-bd2 bg-sf shadow-[0_18px_50px_rgba(0,0,0,.2)]">
      <div className="flex flex-col gap-0.5 border-b border-bd p-3.5">
        <span className="text-[13.5px] font-semibold">{user.display_name}</span>
        <span className="truncate text-[12px] text-tx3">{user.email}</span>
        <span className="mt-1.5 w-fit bg-infos px-[7px] py-0.5 text-[10.5px] font-semibold uppercase tracking-[.05em] text-info">
          {user.role?.name ?? 'No role'}
        </span>
      </div>
      <div className="py-1.5">
        {links.map((link) => (
          <button key={link.href} type="button" role="menuitem" className={row} onClick={() => go(link.href)}>
            <Icon name={link.icon} size={17} className="text-tx3" />
            {link.label}
          </button>
        ))}
      </div>
      <div className="border-t border-bd py-1.5">
        <button type="button" role="menuitem" className={row} onClick={() => void signOut()}>
          <Icon name="logout" size={17} className="text-tx3" />
          Sign out
        </button>
      </div>
    </div>
  );
}

function NotificationsButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const { data } = useApprovalInbox();
  const count = data?.count ?? 0;
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={count ? `Notifications (${count} pending approvals)` : 'Notifications'}
      aria-expanded={open}
      className="relative flex size-[34px] flex-none items-center justify-center border border-bd bg-transparent text-tx hover:bg-sf3"
    >
      <Icon name="notifications" size={19} />
      {count > 0 && (
        <span className="absolute -top-1.5 -right-1.5 flex h-[18px] min-w-[18px] items-center justify-center bg-err px-1 font-mono text-[10px] font-semibold text-white">
          {count > 99 ? '99+' : count}
        </span>
      )}
    </button>
  );
}

function NotificationsPanel({ onClose }: { onClose: () => void }) {
  const { data, loading } = useApprovalInbox();
  const items = data?.results ?? [];
  return (
    <div className="fixed top-[62px] right-3 z-50 flex max-h-[calc(100vh-80px)] w-[410px] max-w-[calc(100vw-24px)] animate-rise flex-col border border-bd2 bg-sf shadow-[0_18px_50px_rgba(0,0,0,.2)]">
      <div className="flex items-center justify-between border-b border-bd px-3.5 py-3">
        <span className="text-[13.5px] font-semibold">Notifications</span>
        <Link href="/settings/approvals" onClick={onClose} className="text-[12px] font-medium">
          All approvals
        </Link>
      </div>
      <div className="overflow-auto">
        {items.map((item) => (
          <Link
            key={item.id}
            href="/settings/approvals"
            onClick={onClose}
            className="flex w-full gap-[11px] border-b border-bd bg-sf2 px-3.5 py-[11px] text-left text-tx hover:bg-sf3 hover:text-tx hover:no-underline"
          >
            <Icon name="approval" size={18} className="mt-px text-warn" />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-[10px] font-semibold uppercase tracking-[.08em] text-tx3">Approval needed</span>
              <span className="text-[12.5px] font-semibold leading-[1.35]">{item.title}</span>
              <span className="text-[11.5px] text-tx3">
                {item.requested_by.display_name} · {formatDateTime(item.requested_at)}
              </span>
            </div>
            <span className="mt-1.5 size-[7px] flex-none bg-ac" />
          </Link>
        ))}
        {!loading && items.length === 0 && (
          <div className="px-4 py-9 text-center text-[12.5px] text-tx3">
            You’re all caught up. Approval requests that need your decision appear here; other
            notifications arrive with the business modules.
          </div>
        )}
      </div>
    </div>
  );
}
