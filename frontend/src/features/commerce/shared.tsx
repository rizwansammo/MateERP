'use client';

import Link from 'next/link';
import { type ReactNode, useState } from 'react';

import { Badge, type Tone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Icon } from '@/components/ui/Icon';
import { Panel, PanelHeader } from '@/components/ui/Panel';
import { Restricted } from '@/components/ui/Restricted';
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { FilterChips, Pager, SearchBox, TableState, TableToolbar } from '@/components/ui/TableKit';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import { invalidate, useQuery } from '@/lib/api/query';
import type { AuditEvent, Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { cn } from '@/lib/cn';
import { formatDate, formatDateTime } from '@/lib/format';
import { useDebounced } from '@/lib/useDebounced';

import type { Journal } from '@/features/accounting/types';
import { useMoney } from '@/features/accounting/shared';

import type { DocumentKind, FiledDocument, JournalRef } from './types';

export { useMoney };

export function useApi<T>(path: string | null) {
  return useQuery(path, () => api.get<T>(path!));
}

/** Refetch every commercial and financial view after a mutation. */
export function refreshCommerce() {
  for (const prefix of ['/sales/', '/billing/', '/purchasing/', '/documents/', '/accounting/', '/banking/', '/approvals/', '/audit/', '/founders/', '/ownership/']) {
    invalidate(prefix);
  }
}

/** A posting key that stays the same for every retry of one user action. */
export function useActionKey() {
  const [key, setKey] = useState(() => crypto.randomUUID());
  return { key, renew: () => setKey(crypto.randomUUID()) };
}

export function today() {
  return new Date().toLocaleDateString('en-CA');
}

/** Run a mutation with a success toast; errors are returned to the caller's banner. */
export async function act<T>(run: () => Promise<T>, message: string | ((result: T) => string)) {
  const result = await run();
  refreshCommerce();
  toast(typeof message === 'function' ? message(result) : message);
  return result;
}

/* ------------------------------------------------------------------ statuses */

const STATUS: Record<string, [string, Tone]> = {
  draft: ['Draft', 'neutral'],
  pending_approval: ['Awaiting approval', 'warn'],
  awaiting_approval: ['Awaiting approval', 'warn'],
  approved: ['Approved', 'info'],
  issued: ['Issued', 'info'],
  partially_paid: ['Partially paid', 'warn'],
  paid: ['Paid', 'ok'],
  credited: ['Credited', 'ok'],
  void: ['Void', 'neutral'],
  cancelled: ['Cancelled', 'neutral'],
  pending_verification: ['Pending verification', 'warn'],
  verified: ['Verified', 'ok'],
  rejected: ['Rejected', 'err'],
  reversed: ['Reversed', 'neutral'],
  posted: ['Posted', 'info'],
  confirmed: ['Confirmed', 'info'],
  partially_invoiced: ['Partially invoiced', 'warn'],
  invoiced: ['Fully invoiced', 'ok'],
  active: ['Active', 'ok'],
  paused: ['Paused', 'warn'],
  completed: ['Completed', 'neutral'],
  on_hold: ['On hold', 'warn'],
  drafted: ['Draft created', 'info'],
  failed: ['Failed', 'err'],
  overdue: ['Overdue', 'err'],
};

export function statusLabel(status: string) {
  return STATUS[status]?.[0] ?? status;
}

export function StatusBadge({ status, overdue = false }: { status: string; overdue?: boolean }) {
  const [label, tone] = overdue ? STATUS.overdue! : (STATUS[status] ?? [status, 'neutral' as Tone]);
  return <Badge tone={tone}>{label}</Badge>;
}

export const KIND_LABEL: Record<DocumentKind, string> = {
  invoice: 'Invoice',
  receipt: 'Money receipt',
  credit_note: 'Credit note',
  bank_proof: 'Bank payment proof',
  client_supporting: 'Supporting document',
  vendor_invoice: 'Vendor invoice',
  vendor_receipt: 'Vendor receipt',
  vendor_supporting: 'Supporting document',
};

export const KIND_ICON: Record<DocumentKind, [string, string]> = {
  invoice: ['picture_as_pdf', 'text-ac'],
  receipt: ['receipt', 'text-ok'],
  credit_note: ['remove_circle', 'text-info'],
  bank_proof: ['account_balance', 'text-warn'],
  client_supporting: ['draft', 'text-tx3'],
  vendor_invoice: ['receipt_long', 'text-ac'],
  vendor_receipt: ['receipt', 'text-ok'],
  vendor_supporting: ['draft', 'text-tx3'],
};

export const METHODS = [
  { value: 'bank_transfer', label: 'Bank transfer' },
  { value: 'cash', label: 'Cash' },
  { value: 'cheque', label: 'Cheque' },
  { value: 'card', label: 'Card' },
  { value: 'mobile_wallet', label: 'Mobile wallet' },
  { value: 'other', label: 'Other' },
];

export function methodLabel(value: string) {
  return METHODS.find((m) => m.value === value)?.label ?? value;
}

/* ------------------------------------------------------------------ gates */

export function Gate({ allow, children, what = 'financial records' }: { allow: boolean; children: ReactNode; what?: string }) {
  return allow ? (
    children
  ) : (
    <Restricted title="Access restricted">Your role does not include {what}.</Restricted>
  );
}

/* ------------------------------------------------------------------ list panel */

export interface Column<T> {
  key: string;
  label: string;
  align?: 'left' | 'right';
  className?: string;
  render: (row: T) => ReactNode;
}

interface ListPanelProps<T> {
  path: string;
  columns: Column<T>[];
  title?: string;
  subtitle?: ReactNode;
  filters?: { value: string; label: string; query?: string }[];
  defaultFilter?: string;
  search?: string | false;
  empty?: ReactNode;
  actions?: ReactNode;
  pageSize?: number;
  rowKey?: (row: T) => string | number;
}

/** Server-paginated table with the prototype DataTable chrome. */
export function ListPanel<T extends { id: number | string }>({
  path,
  columns,
  title,
  subtitle,
  filters,
  defaultFilter,
  search = 'Search…',
  empty = 'Nothing here yet.',
  actions,
  pageSize = 25,
  rowKey = (row) => row.id,
}: ListPanelProps<T>) {
  const [filter, setFilter] = useState(defaultFilter ?? filters?.[0]?.value ?? '');
  const [term, setTerm] = useState('');
  const [page, setPage] = useState(1);
  const q = useDebounced(term, 250);
  const active = filters?.find((f) => f.value === filter);
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (q) params.set('search', q);
  for (const [k, v] of new URLSearchParams(active?.query ?? '')) params.set(k, v);
  const joiner = path.includes('?') ? '&' : '?';
  const list = useApi<Page<T>>(`${path}${joiner}${params.toString()}`);
  return (
    <Panel>
      {(title || filters || search || actions) && (
        <TableToolbar title={title} subtitle={subtitle}>
          {filters && (
            <FilterChips
              label="Filter"
              value={filter}
              onChange={(v) => {
                setFilter(v);
                setPage(1);
              }}
              options={filters.map((f) => ({ value: f.value, label: f.label }))}
            />
          )}
          {search !== false && (
            <SearchBox
              value={term}
              onChange={(v) => {
                setTerm(v);
                setPage(1);
              }}
              placeholder={search}
            />
          )}
          {actions}
        </TableToolbar>
      )}
      <Table>
        <THead>
          <TR>
            {columns.map((c) => (
              <TH key={c.key} align={c.align}>
                {c.label}
              </TH>
            ))}
          </TR>
        </THead>
        <TBody>
          <TableState
            colSpan={columns.length}
            loading={list.loading && !list.data}
            error={list.error ? errorMessage(list.error) : null}
            empty={list.data && list.data.count === 0 ? empty : null}
          >
            {list.data?.results.map((row) => (
              <TR key={rowKey(row)}>
                {columns.map((c) => (
                  <TD key={c.key} align={c.align} className={c.className}>
                    {c.render(row)}
                  </TD>
                ))}
              </TR>
            ))}
          </TableState>
        </TBody>
      </Table>
      {list.data && (
        <Pager page={list.data.page} totalPages={list.data.total_pages} count={list.data.count} pageSize={pageSize} onPage={setPage} />
      )}
    </Panel>
  );
}

/** Primary cell: link title with a muted second line. */
export function Primary({ href, title, sub, mono = false }: { href?: string; title: ReactNode; sub?: ReactNode; mono?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col">
      {href ? (
        <Link href={href} className={cn('font-medium', mono && 'font-mono text-[12.5px]')}>
          {title}
        </Link>
      ) : (
        <span className={cn('font-medium', mono && 'font-mono text-[12.5px]')}>{title}</span>
      )}
      {sub && <span className="text-[11.5px] text-tx3">{sub}</span>}
    </div>
  );
}

/* ------------------------------------------------------------------ lifecycle */

export function Lifecycle({ steps }: { steps: { label: string; sub: string; done: boolean }[] }) {
  return (
    <div className="flex flex-wrap border border-bd bg-sf">
      {steps.map((s) => (
        <div key={s.label} className="relative flex min-w-[130px] flex-1 items-center gap-[9px] border-r border-bd px-3.5 py-[11px] last:border-r-0">
          <span className={cn('absolute inset-x-0 bottom-0 h-0.5', s.done ? 'bg-ac' : 'bg-transparent')} />
          <span className={cn('flex size-[22px] flex-none items-center justify-center', s.done ? 'bg-pr text-prt' : 'bg-sf3 text-tx3')}>
            <Icon name={s.done ? 'check' : 'radio_button_unchecked'} size={15} />
          </span>
          <span className="flex min-w-0 flex-col">
            <span className={cn('text-[12px] font-semibold', s.done ? 'text-tx' : 'text-tx3')}>{s.label}</span>
            <span className="whitespace-nowrap text-[11px] text-tx3">{s.sub}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ cards */

export function Card({ title, subtitle, actions, children }: { title: string; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <Panel>
      <PanelHeader title={title} subtitle={subtitle} actions={actions} />
      {children}
    </Panel>
  );
}

function JournalBlock({ journal }: { journal: JournalRef }) {
  const money = useMoney();
  const detail = useApi<Journal>(`/accounting/journals/${journal.id}/`);
  return (
    <div className="border-b border-bd px-4 py-2.5 last:border-b-0">
      <div className="mb-1.5 flex justify-between gap-2.5 text-[12px]">
        <Link href={`/banking/journals/${journal.id}`} className="font-semibold">
          {detail.data ? `${detail.data.description}` : journal.number} · {journal.number}
        </Link>
        <span className="text-tx3">{detail.data ? formatDate(detail.data.posting_date) : ''}</span>
      </div>
      {detail.data?.lines.map((l) => (
        <div key={l.id} className="grid grid-cols-[minmax(0,1fr)_110px_110px] py-0.5 text-[11.5px]">
          <span className={cn('truncate text-tx2', positive(l.base_credit) && 'pl-3.5')}>
            <span className="font-mono text-tx3">{l.account_code}</span> {l.account_name}
          </span>
          <span className="text-right tabular-nums">{positive(l.base_debit) ? money(l.base_debit, detail.data?.base_currency) : ''}</span>
          <span className="text-right tabular-nums">{positive(l.base_credit) ? money(l.base_credit, detail.data?.base_currency) : ''}</span>
        </div>
      ))}
    </div>
  );
}

/** Posted journals behind a document, read from the authoritative ledger. */
export function LedgerImpact({ journals, empty }: { journals: (JournalRef | null | undefined)[]; empty: string }) {
  const list = journals.filter((j): j is JournalRef => Boolean(j));
  return (
    <Card title="Accounting impact" subtitle="Posted double-entry journals · base currency">
      {list.length ? list.map((j) => <JournalBlock key={j.id} journal={j} />) : <div className="p-4 text-[12.5px] text-tx3">{empty}</div>}
    </Card>
  );
}

/** Audit trail for one record (requires audit access). */
export function Activity({ targetType, targetId }: { targetType: string; targetId: string | number }) {
  const { can } = useAuth();
  const events = useApi<Page<AuditEvent>>(
    can('audit.view') ? `/audit/events/?target_type=${targetType}&target_id=${targetId}&page_size=12` : null,
  );
  if (!can('audit.view')) return null;
  return (
    <Card title="Activity">
      {events.data?.results.length ? (
        events.data.results.map((e) => (
          <div key={e.id} className="flex gap-2.5 border-b border-bd px-4 py-[9px] text-[12px] last:border-b-0">
            <span className="mt-1.5 size-1.5 flex-none bg-ac" />
            <div className="min-w-0 flex-1">
              <div className="text-tx">
                {e.action.split('.').pop()?.replace(/_/g, ' ')} <span className="text-tx3">{e.reason}</span>
              </div>
              <div className="text-[11px] text-tx3">
                {e.actor_label || 'System'} · {formatDateTime(e.occurred_at)}
              </div>
            </div>
          </div>
        ))
      ) : (
        <div className="p-4 text-[12.5px] text-tx3">{events.loading ? 'Loading…' : 'No recorded activity.'}</div>
      )}
    </Card>
  );
}

/** Files filed against a record (restricted proofs are hidden by the server). */
export function DocumentBundle({
  query,
  title = 'Document bundle',
  empty,
  actions,
  onOpen,
}: {
  query: string;
  title?: string;
  empty: string;
  actions?: ReactNode;
  onOpen: (doc: FiledDocument) => void;
}) {
  const { can } = useAuth();
  const docs = useApi<Page<FiledDocument>>(
    can('finance.view') || can('documents.client.view') || can('documents.vendor.view') ? `/documents/?${query}&page_size=50` : null,
  );
  return (
    <Card title={title} actions={actions}>
      {docs.data?.results.length ? (
        docs.data.results.map((d) => {
          const [icon, tone] = KIND_ICON[d.kind];
          return (
            <button
              key={d.id}
              type="button"
              onClick={() => onOpen(d)}
              className="flex w-full items-center gap-2.5 border-b border-bd bg-transparent px-4 py-[9px] text-left text-tx last:border-b-0 hover:bg-sfh"
            >
              <Icon name={icon} size={18} className={tone} />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[12.5px] font-medium">{d.title}</span>
                <span className="text-[11px] text-tx3">
                  {KIND_LABEL[d.kind]}
                  {d.restricted ? ' · restricted' : ''}
                </span>
              </span>
              <span className="text-[11px] text-tx3">{formatDate(d.document_date)}</span>
            </button>
          );
        })
      ) : (
        <div className="p-4 text-[12.5px] text-tx3">{docs.loading && docs.data === undefined ? 'Loading…' : empty}</div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ official PDFs */

export function PdfState({
  status,
  url,
  error,
  onRetry,
  canRetry,
}: {
  status: 'none' | 'pending' | 'ready' | 'failed';
  url: string | null;
  error?: string;
  onRetry: () => Promise<unknown>;
  canRetry: boolean;
}) {
  const [busy, setBusy] = useState(false);
  if (status === 'ready' && url) {
    return (
      <div className="flex gap-1.5">
        <a href={url} target="_blank" rel="noreferrer" className="inline-flex h-[28px] items-center gap-[5px] border border-bd2 bg-sf px-2.5 text-[12px] font-medium text-tx hover:bg-sf3 hover:no-underline">
          <Icon name="open_in_full" size={16} /> Open
        </a>
        <a href={`${url}?download=1`} className="inline-flex h-[28px] items-center gap-[5px] border border-bd2 bg-sf px-2.5 text-[12px] font-medium text-tx hover:bg-sf3 hover:no-underline">
          <Icon name="picture_as_pdf" size={16} /> PDF
        </a>
      </div>
    );
  }
  if (status === 'none') return null;
  return (
    <div className="flex items-center gap-2 text-[12px] text-tx3">
      <span>{status === 'failed' ? `PDF generation failed${error ? ` (${error})` : ''}` : 'PDF is being generated'}</span>
      {canRetry && (
        <Button
          size="xs"
          icon="refresh"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await act(onRetry, 'PDF generation retried');
            } catch (e) {
              toast(errorMessage(e), 'err');
            } finally {
              setBusy(false);
            }
          }}
        >
          Retry
        </Button>
      )}
    </div>
  );
}

/** Small "N days overdue" helper for list rows. */
export function overdueDays(due: string) {
  const ms = Date.now() - new Date(`${due}T00:00:00`).getTime();
  return Math.max(0, Math.floor(ms / 86_400_000));
}

/** True when an exact decimal string is greater than zero (no float conversion). */
export function positive(value: string | null | undefined) {
  return Boolean(value) && !value!.startsWith('-') && !/^0*(\.0*)?$/.test(value!);
}

/** Exact sum of decimal strings, returned with six decimal places. */
export function sumDecimals(values: (string | null | undefined)[]) {
  let total = 0n;
  for (const v of values) {
    if (!v) continue;
    const negative = v.startsWith('-');
    const [w = '0', f = ''] = v.replace('-', '').split('.');
    const n = BigInt(w + f.padEnd(6, '0').slice(0, 6));
    total += negative ? -n : n;
  }
  const sign = total < 0n ? '-' : '';
  const abs = total < 0n ? -total : total;
  return `${sign}${abs / 1_000_000n}.${(abs % 1_000_000n).toString().padStart(6, '0')}`;
}

/** "11000.500000" → "11000.5" for editing; integers keep their zeros. */
export function trimDecimal(value: string | null | undefined) {
  if (!value) return '';
  return value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
}
