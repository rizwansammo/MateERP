'use client';

import Link from 'next/link';
import type { MouseEvent } from 'react';

import { Icon } from '@/components/ui/Icon';
import { cn } from '@/lib/cn';
import { useModules } from '@/lib/api/hooks';
import { useAuth } from '@/lib/auth/AuthProvider';
import {
  NAVIGATION,
  canAccess,
  isVisible,
  itemHref,
  resolveRoute,
  subHref,
} from '@/lib/navigation';
import { useSidebarMode } from '@/lib/preferences';

interface SidebarNavProps {
  pathname: string;
  /** Explicit open/closed choices made by the user for item sub-menus. */
  openOverrides: Record<string, boolean>;
  onToggle: (itemId: string, open: boolean) => void;
  onNavigate: () => void;
}

/** True when the 64px compact sidebar is actually in effect (desktop widths only). */
function compactInEffect(mode: string): boolean {
  return mode === 'compact' && window.matchMedia('(min-width: 1000px)').matches;
}

export function SidebarNav({ pathname, openOverrides, onToggle, onNavigate }: SidebarNavProps) {
  const { mode } = useSidebarMode();
  const { can } = useAuth();
  const { states: modules } = useModules();
  const route = resolveRoute(pathname);
  const groups = NAVIGATION.map((group) => ({
    ...group,
    items: group.items.filter((item) => isVisible(item, modules)),
  })).filter((group) => group.items.length > 0);

  return (
    <nav aria-label="Main navigation" className="flex-1 overflow-y-auto overflow-x-hidden pt-1.5 pb-4">
      {groups.map((group) => (
        <div key={group.label} role="group" aria-label={group.label}>
          <div className="overflow-hidden whitespace-nowrap px-5 pt-3.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[.14em] text-sb-muted compact:text-center">
            <span className="compact:hidden">{group.label}</span>
            <span aria-hidden="true" className="hidden compact:inline">
              ·
            </span>
          </div>

          {group.items.map((item) => {
            const active = route?.item.id === item.id;
            const subs = (item.subs ?? []).filter((s) => isVisible(s, modules));
            const hasSubs = subs.length > 0;
            const locked = !canAccess(item, can);
            const isOpen = hasSubs && (openOverrides[item.id] ?? active);

            const onItemClick = (event: MouseEvent<HTMLAnchorElement>) => {
              if (hasSubs && !compactInEffect(mode)) {
                if (active) {
                  // Clicking the active module only folds/unfolds its sub-menu.
                  event.preventDefault();
                  onToggle(item.id, !isOpen);
                  return;
                }
                onToggle(item.id, true);
              }
              onNavigate();
            };

            return (
              <div key={item.id}>
                <Link
                  href={item.id==='founder' && !can('founder.view') ? '/founder/settlements' : item.id==='ownership' && !can('ownership.view') && !can('ownership.manage') ? '/ownership/history' : itemHref(item)}
                  onClick={onItemClick}
                  aria-current={active ? 'page' : undefined}
                  aria-expanded={hasSubs ? isOpen : undefined}
                  title={mode === 'compact' ? item.label : undefined}
                  data-active={active}
                  className={cn(
                    'relative flex h-9 w-full items-center gap-[11px] px-[18px] text-left text-[13px] leading-[normal] hover:bg-sb-h hover:text-white hover:no-underline',
                    'compact:justify-center compact:px-0',
                    active ? 'bg-sb-a font-semibold text-white' : 'font-medium text-sb-tx',
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      'absolute top-1.5 bottom-1.5 left-0 w-0.5',
                      active ? 'bg-brand' : 'bg-transparent',
                    )}
                  />
                  <Icon
                    name={item.icon}
                    size={19}
                    className={active ? 'text-brand' : locked ? 'text-sb-muted' : 'text-sb-tx2'}
                  />
                  <span className="min-w-0 flex-1 truncate compact:sr-only">{item.label}</span>
                  {locked && (
                    <Icon name="lock" size={14} className="text-sb-muted compact:hidden" />
                  )}
                  {hasSubs && (
                    <Icon
                      name="expand_more"
                      size={16}
                      className={cn(
                        'text-sb-muted transition-transform duration-150 compact:hidden',
                        isOpen && 'rotate-180',
                      )}
                    />
                  )}
                </Link>

                {isOpen && hasSubs && (
                  <div className="relative mt-0.5 mb-1.5 ml-[29px] border-l border-sb-bd compact:hidden">
                    {subs.map((s) => {
                      const current = active && route?.sub?.slug === s.slug;
                      return (
                        <Link
                          key={s.slug}
                          href={subHref(item, s)}
                          onClick={onNavigate}
                          aria-current={current ? 'page' : undefined}
                          className={cn(
                            '-ml-px flex h-[30px] w-full items-center gap-2 whitespace-nowrap border-l pr-3 pl-4 text-[12.5px] leading-[normal] hover:text-white hover:no-underline',
                            current
                              ? 'border-brand font-semibold text-white'
                              : 'border-transparent font-normal text-sb-tx2',
                          )}
                        >
                          {s.label}
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
