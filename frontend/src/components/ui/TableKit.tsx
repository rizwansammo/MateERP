'use client';

import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

import { Icon } from './Icon';
import { Spinner } from './Spinner';

/*
 * Data-table chrome from the prototype DataTable: header toolbar with title,
 * filter chips, search and actions; sortable heads; pager footer.
 */

interface ToolbarProps {
  title?: string;
  subtitle?: ReactNode;
  children?: ReactNode;
}

export function TableToolbar({ title, subtitle, children }: ToolbarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-bd px-3.5 py-3">
      {(title || subtitle) && (
        <div className="flex min-w-0 flex-col gap-0.5">
          {title && <h2 className="m-0 text-[13.5px] font-semibold text-tx">{title}</h2>}
          {subtitle && <div className="text-[12px] text-tx3">{subtitle}</div>}
        </div>
      )}
      <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

interface FilterChipsProps<T extends string> {
  value: T;
  options: { value: T; label: string; count?: number }[];
  onChange: (value: T) => void;
  label: string;
}

export function FilterChips<T extends string>({ value, options, onChange, label }: FilterChipsProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap border border-bd2">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={cn(
              'flex h-[30px] items-center gap-1.5 border-r border-bd px-[11px] text-[12px] font-medium whitespace-nowrap last:border-r-0',
              active ? 'bg-tx text-sf' : 'bg-transparent text-tx2 hover:bg-sf3',
            )}
          >
            {o.label}
            {o.count !== undefined && (
              <span className={cn('font-mono text-[10.5px] font-medium', active ? 'text-sf' : 'text-tx3')}>{o.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

interface SearchBoxProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
}

export function SearchBox({ value, onChange, placeholder = 'Search…', label = 'Search table' }: SearchBoxProps) {
  return (
    <div className="flex h-[30px] w-[220px] max-w-full items-center gap-1.5 border border-bd2 bg-inp px-2 focus-within:border-ac">
      <Icon name="search" size={16} className="text-tx3" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className="min-w-0 flex-1 border-0 bg-transparent text-[12.5px] text-tx outline-none placeholder:text-tx3"
      />
    </div>
  );
}

export type SortDir = 'asc' | 'desc';

interface SortHeadProps {
  label: string;
  active: boolean;
  dir: SortDir;
  onSort: () => void;
  align?: 'left' | 'right';
}

/** Sortable column header (place inside a <th>). */
export function SortHead({ label, active, dir, onSort, align = 'left' }: SortHeadProps) {
  return (
    <button
      type="button"
      onClick={onSort}
      aria-label={`Sort by ${label}${active ? (dir === 'asc' ? ', ascending' : ', descending') : ''}`}
      className={cn(
        'inline-flex items-center gap-[3px] bg-transparent text-[10.5px] font-semibold uppercase tracking-[.07em] whitespace-nowrap',
        active ? 'text-tx' : 'text-tx3 hover:text-tx2',
        align === 'right' && 'flex-row-reverse',
      )}
    >
      {label}
      {active && <Icon name={dir === 'asc' ? 'arrow_upward' : 'arrow_downward'} size={13} />}
    </button>
  );
}

interface PagerProps {
  page: number;
  totalPages: number;
  count: number;
  pageSize: number;
  onPage: (page: number) => void;
}

export function Pager({ page, totalPages, count, pageSize, onPage }: PagerProps) {
  if (count === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(count, page * pageSize);
  const btn =
    'flex size-7 items-center justify-center border border-bd2 bg-sf text-tx2 hover:bg-sf3 disabled:cursor-not-allowed disabled:opacity-40';
  return (
    <div className="flex items-center justify-between gap-2.5 px-3.5 py-2 text-[12px] text-tx3">
      <span className="tabular-nums">{`${from}–${to} of ${count}`}</span>
      <div className="flex gap-1">
        <button type="button" className={btn} aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <Icon name="chevron_left" size={16} />
        </button>
        <button type="button" className={btn} aria-label="Next page" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
          <Icon name="chevron_right" size={16} />
        </button>
      </div>
    </div>
  );
}

/** Loading / error / empty states for a table body. */
export function TableState({ loading, error, empty, colSpan, children }: {
  loading: boolean;
  error?: string | null;
  empty?: ReactNode;
  colSpan: number;
  children?: ReactNode;
}) {
  if (!loading && !error && !empty) return <>{children}</>;
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-8 text-center text-[12.5px] text-tx3">
        {loading ? (
          <span className="inline-flex items-center gap-2"><Spinner /> Loading…</span>
        ) : error ? (
          <span role="alert" className="text-err">{error}</span>
        ) : (
          empty
        )}
      </td>
    </tr>
  );
}
