'use client';

import { useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input, Select } from '@/components/ui/Input';
import { DialogActions, DialogFooter, Drawer } from '@/components/ui/Overlay';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel } from '@/components/ui/Panel';
import { FilterChips, Pager, SearchBox, TableState, TableToolbar } from '@/components/ui/TableKit';
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { api, errorMessage } from '@/lib/api/client';
import { useQuery } from '@/lib/api/query';
import type { AuditEvent, Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDateTime, titleCase } from '@/lib/format';
import { useDebounced } from '@/lib/useDebounced';

import { Gate } from '../Gate';

const ACTION_LABELS: Record<string, string> = {
  'auth.login.succeeded': 'Signed in',
  'auth.login.failed': 'Sign-in failed',
  'auth.login.throttled': 'Sign-in throttled',
  'auth.logout': 'Signed out',
  'auth.password.changed': 'Password changed',
  'auth.password.change_failed': 'Password change failed',
  'auth.locks_cleared': 'Sign-in locks cleared',
  'user.created': 'User created',
  'user.updated': 'User updated',
  'user.role_changed': 'Role assigned',
  'user.deactivated': 'User deactivated',
  'user.reactivated': 'User reactivated',
  'user.password_reset': 'Temporary password issued',
  'user.profile_updated': 'Profile updated',
  'user.admin_bootstrapped': 'Administrator created (setup)',
  'role.created': 'Role created',
  'role.updated': 'Role updated',
  'role.permissions_changed': 'Permissions changed',
  'company.created': 'Company profile created',
  'company.updated': 'Company profile updated',
  'company.logo_added': 'Company logo added',
  'company.logo_replaced': 'Company logo replaced',
  'company.logo_removed': 'Company logo removed',
  'settings.business_updated': 'Business settings updated',
  'settings.module_enabled': 'Module enabled',
  'settings.module_disabled': 'Module disabled',
  'branding.draft_updated': 'Branding draft saved',
  'branding.draft_discarded': 'Branding draft discarded',
  'branding.asset_uploaded': 'Branding asset uploaded',
  'branding.asset_removed': 'Branding asset removed',
  'branding.published': 'Branding published',
  'branding.restore_requested': 'Branding version restored',
  'approval.requested': 'Approval requested',
  'approval.approved': 'Request approved',
  'approval.rejected': 'Request rejected',
  'approval.cancelled': 'Request withdrawn',
  'approval.decision_denied': 'Approval attempt denied',
  'approval.policy_updated': 'Approval rule changed',
};

export function actionLabel(code: string): string {
  return ACTION_LABELS[code] ?? titleCase(code.replace(/[._]/g, ' '));
}

const OUTCOME_TONE = { success: 'ok', failure: 'err', denied: 'warn' } as const;

export function AuditPage() {
  return (
    <Gate anyOf={['audit.view']}>
      <AuditContent />
    </Gate>
  );
}

function AuditContent() {
  const { user } = useAuth();
  const facets = useQuery('/audit/facets/', () => api.get<{ categories: string[]; actions: string[] }>('/audit/facets/'));
  const [category, setCategory] = useState('all');
  const [outcome, setOutcome] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<AuditEvent | null>(null);
  const q = useDebounced(search.trim());
  const params = { category: category === 'all' ? '' : category, outcome, date_from: from, date_to: to, q, page, page_size: user.preferences.rows_per_page ?? 25 };
  const key = `/audit/events/?${new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString()}`;
  const events = useQuery(key, () => api.get<Page<AuditEvent>>('/audit/events/', params));
  const reset = (fn: () => void) => { fn(); setPage(1); };
  const data = events.data;

  return (
    <PageContainer>
      <PageHeader eyebrow="Settings" title="Audit log" description="Who did what, when — with previous and new values and outcomes. Entries are append-only and cannot be edited or deleted. Secrets are never recorded." />
      <Panel>
        <TableToolbar title="Events" subtitle={data ? `${data.count} matching events` : undefined}>
          <FilterChips label="Category" value={category} onChange={(v) => reset(() => setCategory(v))}
            options={[{ value: 'all', label: 'All' }, ...(facets.data?.categories ?? []).map((c) => ({ value: c, label: titleCase(c) }))]} />
        </TableToolbar>
        <div className="flex flex-wrap items-center gap-2 border-b border-bd px-3.5 py-2.5">
          <span className="inline-block w-[150px]">
          <Select aria-label="Outcome" value={outcome} onChange={(e) => reset(() => setOutcome(e.target.value))} controlSize="sm">
            <option value="">All outcomes</option>
            <option value="success">Success</option>
            <option value="failure">Failure</option>
            <option value="denied">Denied</option>
          </Select>
          </span>
          <label className="flex items-center gap-1.5 text-[12px] text-tx3">From
            <span className="inline-block w-[150px]"><Input type="date" aria-label="From date" value={from} max={to || undefined} onChange={(e) => reset(() => setFrom(e.target.value))} controlSize="sm" /></span>
          </label>
          <label className="flex items-center gap-1.5 text-[12px] text-tx3">To
            <span className="inline-block w-[150px]"><Input type="date" aria-label="To date" value={to} min={from || undefined} onChange={(e) => reset(() => setTo(e.target.value))} controlSize="sm" /></span>
          </label>
          <div className="ml-auto"><SearchBox value={search} onChange={(v) => reset(() => setSearch(v))} placeholder="User, record, action, request id…" label="Search audit log" /></div>
        </div>
        <Table>
          <THead>
            <TR>
              <TH>Date &amp; time</TH>
              <TH>User</TH>
              <TH>Action</TH>
              <TH>Record</TH>
              <TH>Outcome</TH>
            </TR>
          </THead>
          <TBody>
            <TableState colSpan={5} loading={events.loading && !data} error={events.error ? errorMessage(events.error) : null} empty={data?.count === 0 ? 'No events match these filters.' : null}>
              {data?.results.map((e) => (
                <TR key={e.id} className="cursor-pointer" onClick={() => setDetail(e)}>
                  <TD className="whitespace-nowrap text-tx2">{formatDateTime(e.occurred_at)}</TD>
                  <TD>{e.actor_label || <span className="text-tx3">System / anonymous</span>}</TD>
                  <TD className={e.outcome === 'success' ? '' : 'text-err'}>{actionLabel(e.action)}</TD>
                  <TD>
                    <div>{e.target_label || '—'}</div>
                    {e.target_type && <div className="text-[11.5px] text-tx3">{e.target_type}</div>}
                  </TD>
                  <TD><Badge tone={OUTCOME_TONE[e.outcome]}>{e.outcome}</Badge></TD>
                </TR>
              ))}
            </TableState>
          </TBody>
        </Table>
        {data && <Pager page={data.page} totalPages={data.total_pages} count={data.count} pageSize={data.page_size} onPage={setPage} />}
      </Panel>
      {detail && <AuditDetail event={detail} onClose={() => setDetail(null)} />}
    </PageContainer>
  );
}

function AuditDetail({ event, onClose }: { event: AuditEvent; onClose: () => void }) {
  const rows: [string, React.ReactNode][] = [
    ['When', formatDateTime(event.occurred_at)],
    ['User', event.actor_label || 'System / anonymous'],
    ['Action', <span key="a">{actionLabel(event.action)} <span className="font-mono text-[11px] text-tx3">{event.action}</span></span>],
    ['Record', [event.target_label, event.target_type, event.target_id].filter(Boolean).join(' · ') || '—'],
    ['Outcome', <Badge key="o" tone={OUTCOME_TONE[event.outcome]}>{event.outcome}</Badge>],
    ['Reason', event.reason || '—'],
    ['Client IP', event.ip_address || '—'],
    ['Request ID', <span key="r" className="font-mono text-[11.5px]">{event.request_id || '—'}</span>],
    ['Event ID', <span key="i" className="font-mono text-[11.5px]">{event.id}</span>],
  ];
  return (
    <Drawer open onClose={onClose} width={600} eyebrow="Audit event" title={actionLabel(event.action)}
      footer={<DialogFooter><DialogActions><Button onClick={onClose}>Close</Button></DialogActions></DialogFooter>}>
      <dl className="m-0">
        {rows.map(([l, v]) => (
          <div key={l} className="flex justify-between gap-4 border-b border-bd py-2 text-[12.5px]">
            <dt className="text-tx3">{l}</dt>
            <dd className="m-0 text-right">{v}</dd>
          </div>
        ))}
      </dl>
      {(event.before || event.after) && (
        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {(['before', 'after'] as const).map((side) => (
            <div key={side} className="flex flex-col gap-1.5">
              <span className="text-[10.5px] font-semibold uppercase tracking-[.08em] text-tx3">{side === 'before' ? 'Previous' : 'New'}</span>
              <pre className="m-0 max-h-[320px] overflow-auto border border-bd bg-sf2 p-2.5 font-mono text-[11.5px] leading-normal whitespace-pre-wrap text-tx">
                {event[side] ? JSON.stringify(event[side], null, 2) : '—'}
              </pre>
            </div>
          ))}
        </div>
      )}
    </Drawer>
  );
}
