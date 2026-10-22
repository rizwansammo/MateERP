'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';

import { Icon } from '@/components/ui/Icon';
import { useAuth } from '@/lib/auth/AuthProvider';
import { NAVIGATION, CURRENT_PHASE, canAccess, itemHref, subHref } from '@/lib/navigation';

type SearchResult = { category: string; title: string; description: string; href: string };
type Selection = SearchResult & { icon: string };

export function GlobalSearch({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { can } = useAuth();
  const ref = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [active, setActive] = useState(0);
  const pages = useMemo(() => NAVIGATION.flatMap((group) => group.items
    .filter((item) => item.phase <= CURRENT_PHASE && canAccess(item, can))
    .flatMap((item) => {
      const parent = { category: group.label, title: item.label, description: item.summary, href: itemHref(item), icon: item.icon };
      const children = (item.subs ?? [])
        .filter((sub) => (sub.phase ?? item.phase) <= CURRENT_PHASE)
        .map((sub) => ({ category: item.label, title: sub.label, description: item.summary, href: subHref(item, sub), icon: item.icon }));
      return [parent, ...children];
    })), [can]);

  useEffect(() => { ref.current?.focus(); }, []);
  useEffect(() => {
    if (query.trim().length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError('');
      fetch('/api/v1/reporting/search/?q=' + encodeURIComponent(query.trim()), {
        credentials: 'same-origin', signal: controller.signal, headers: { Accept: 'application/json' },
      })
        .then(async (res) => {
          if (!res.ok) throw new Error('Unable to search records right now.');
          return (await res.json()) as SearchResult[];
        })
        .then(setResults)
        .catch((e: unknown) => {
          if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Search unavailable.');
        })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 240);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);

  const phrase = query.trim().toLowerCase();
  const pageMatches = phrase
    ? pages.filter((page) => (page.title + ' ' + page.category + ' ' + page.description).toLowerCase().includes(phrase)).slice(0, 9)
    : pages.filter((page) => ['/dashboard', '/sales/invoices', '/banking/accounts', '/reports'].includes(page.href)).slice(0, 6);
  const items: Selection[] = [
    ...pageMatches,
    ...results.map((record) => ({ ...record, icon: 'description' })),
  ];
  const pick = (href: string) => { onClose(); router.push(href); };
  return (
    <div className="fixed inset-0 z-[80] flex justify-center bg-black/45 px-3 pt-[min(12vh,105px)]" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <section role="dialog" aria-modal="true" aria-label="Search MateERP" className="flex h-fit max-h-[min(78vh,680px)] w-full max-w-[680px] flex-col border border-bd2 bg-sf shadow-[0_28px_90px_rgba(0,0,0,.28)]">
        <div className="flex items-center gap-3 border-b border-bd px-4 py-3">
          <Icon name="search" size={22} className="text-tx3" />
          <input ref={ref} aria-label="Search pages and records" autoComplete="off"
            className="min-w-0 flex-1 border-0 bg-transparent text-[14px] text-tx outline-none placeholder:text-tx3"
            placeholder="Find pages, customers, invoices, documents…" value={query}
            onChange={(e) => { setQuery(e.target.value); setActive(0); setResults([]); setLoading(false); setError(''); }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') onClose();
              if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(i + 1, items.length - 1)); }
              if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
              if (e.key === 'Enter' && items.length) { e.preventDefault(); pick(items[Math.min(active, items.length - 1)]!.href); }
            }}
          />
          <button type="button" onClick={onClose} className="border border-bd px-2 py-1 text-[11px] text-tx3 hover:bg-sf3" aria-label="Close search">Esc</button>
        </div>
        <div className="overflow-y-auto p-2" role="listbox" aria-label="Search results">
          {loading && <p className="px-3 py-2 text-[12px] text-tx3">Searching records…</p>}
          {error && <p role="alert" className="px-3 py-2 text-[12px] text-err">{error}</p>}
          {items.map((item, i) => (
            <button type="button" role="option" aria-selected={active === i} key={item.href + item.title + i}
              onMouseEnter={() => setActive(i)} onClick={() => pick(item.href)}
              className={'flex w-full items-center gap-3 px-3 py-2.5 text-left ' + (active === i ? 'bg-sf3' : 'hover:bg-sf2')}>
              <Icon name={item.icon} size={19} className="shrink-0 text-tx3" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] font-semibold text-tx">{item.title}</span>
                <span className="block truncate text-[11px] text-tx3">{item.category} · {item.description}</span>
              </span>
              <Icon name="north_east" size={15} className="text-tx3" />
            </button>
          ))}
          {!loading && !error && !items.length && (
            <p className="px-3 py-9 text-center text-[12.5px] text-tx3">No matching pages or authorized records.</p>
          )}
        </div>
        <div className="flex justify-between border-t border-bd px-4 py-2 text-[11px] text-tx3">
          <span>↑ ↓ Navigate · Enter Open</span><span>Only records permitted to your role appear.</span>
        </div>
      </section>
    </div>
  );
}

const CREATE_ACTIONS = [
  { label: 'New invoice', icon: 'receipt_long', href: '/sales/invoices/new', permission: 'invoices.create' },
  { label: 'New customer', icon: 'person_add', href: '/sales/customers?new=1', permission: 'sales.manage' },
  { label: 'New vendor bill', icon: 'receipt', href: '/purchases/bills?new=1', permission: 'bills.manage' },
  { label: 'New supplier', icon: 'storefront', href: '/purchases/vendors?new=1', permission: 'vendors.manage' },
  { label: 'New expense', icon: 'payments', href: '/purchases/expenses?new=1', permission: 'expenses.manage' },
  { label: 'New journal entry', icon: 'menu_book', href: '/banking/journals?new=1', permission: 'accounting.manage' },
];

export function QuickCreate({ onClose }: { onClose: () => void }) {
  const { can } = useAuth();
  const actions = CREATE_ACTIONS.filter((action) => can(action.permission));
  return (
    <div role="menu" aria-label="Create new record" className="absolute top-10 right-0 z-50 w-[256px] border border-bd2 bg-sf py-1.5 shadow-[0_18px_50px_rgba(0,0,0,.2)]">
      <p className="px-3 py-2 text-[10.5px] font-bold uppercase tracking-[.1em] text-tx3">Quick create</p>
      {actions.map((action) => (
        <Link key={action.href} role="menuitem" href={action.href} onClick={onClose}
          className="flex items-center gap-2.5 px-3 py-2.5 text-[12.5px] text-tx hover:bg-sf3 hover:no-underline">
          <Icon name={action.icon} size={18} className="text-tx3" />{action.label}
        </Link>
      ))}
      {!actions.length && <p className="px-3 py-3 text-[12px] text-tx3">Your role has no record-creation permissions.</p>}
    </div>
  );
}
