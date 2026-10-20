'use client';
import Link from 'next/link';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Banner } from '@/components/ui/Banner';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { useConfig } from '@/features/accounting/shared';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { LinesEditor, Totals, blankLine, toEditLines, toPayload, useCalculation } from '@/features/commerce/lines';
import { Card, ListPanel, Primary, StatusBadge, act, today, useApi } from '@/features/commerce/shared';
import type { Customer, Run, Schedule } from '@/features/commerce/types';

export const FREQUENCIES = ['weekly', 'monthly', 'quarterly', 'yearly'].map(value => ({ value, label: value[0]!.toUpperCase() + value.slice(1) }));
function ScheduleDrawer({ schedule, onClose }: { schedule?: Schedule; onClose: () => void }) {
  const customers = useApi<Page<Customer>>('/sales/customers/?page_size=100'); const config = useConfig();
  const initialLines = schedule ? toEditLines(schedule.template.lines, 'revenue_account_id') : [blankLine()];
  const [lines, setLines] = useState(initialLines);
  const [currency, setCurrency] = useState(schedule?.currency ?? config.data?.base_currency ?? '');
  const [start, setStart] = useState(schedule?.start_date ?? today());
  const calc = useCalculation({ currency, date: start, lines, pricesIncludeTax: schedule?.template.prices_include_tax ?? false });
  const detail = useApi<Schedule>(schedule ? `/billing/recurring/${schedule.id}/` : null);
  return <FormDrawer title={schedule ? `Edit ${schedule.name}` : 'New recurring invoice'} eyebrow="Recurring billing" width={1000} onClose={onClose}
    initial={{ name: schedule?.name ?? '', customer_id: String(schedule?.customer_id ?? ''), currency, frequency: schedule?.frequency ?? 'monthly', interval: String(schedule?.interval ?? 1), start_date: start, end_date: schedule?.end_date ?? '', due_days: String(schedule?.due_days ?? 30), auto_issue: schedule?.auto_issue ?? false, notes: schedule?.template.notes ?? '' }}
    extraDirty={JSON.stringify(lines) !== JSON.stringify(initialLines)} onValues={v => { setCurrency(String(v.currency)); setStart(String(v.start_date)); }}
    fields={[
      { key: 'name', label: 'Schedule name', required: true },
      { key: 'customer_id', label: 'Customer', type: 'select', options: [{ value: '', label: 'Select…' }, ...(customers.data?.results ?? []).map(c => ({ value: String(c.id), label: c.name }))] },
      { key: 'currency', label: 'Currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) },
      { key: 'frequency', label: 'Frequency', type: 'select', options: FREQUENCIES }, { key: 'interval', label: 'Every (interval)', type: 'number' },
      { key: 'start_date', label: 'Start date', type: 'date' }, { key: 'end_date', label: 'End date (optional)', type: 'date' }, { key: 'due_days', label: 'Payment due in days', type: 'number' },
      { key: 'auto_issue', label: 'Authorize automatic issuance', type: 'checkbox', hint: 'Requires invoice issuance permission and published branding. Approval requirements still apply.' }, { key: 'notes', label: 'Notes', type: 'textarea' },
    ]} onSave={v => {
      const data = { ...body(v, ['interval', 'due_days']), end_date: v.end_date || null, lines: toPayload(lines, 'revenue_account_id'), ...(schedule ? { revision: schedule.revision } : {}) };
      return schedule ? api.patch(`/billing/recurring/${schedule.id}/`, data) : api.post('/billing/recurring/', data);
    }}>
    <div className="mt-4 border border-bd"><LinesEditor lines={lines} onChange={setLines} currency={currency} calc={calc.result} accountKind="revenue" /><div className="flex flex-wrap justify-between gap-3 p-3"><Button size="sm" onClick={() => setLines(v => [...v, blankLine()])}>Add line</Button><Totals calc={calc.result} currency={currency} error={calc.error} /></div></div>
    {schedule && <div className="mt-4"><RunHistory runs={detail.data?.runs} /></div>}
  </FormDrawer>;
}
export function RunHistory({ runs }: { runs?: Run[] }) {
  return <Card title="Generation history">{runs?.length ? runs.map(r => <div key={r.id} className="flex flex-wrap justify-between gap-2 border-b border-bd p-3 text-[12px]"><span>{formatDate(r.occurrence_date)} · <StatusBadge status={r.status} /></span>{r.invoice_id ? <Link href={`/sales/invoices/${r.invoice_id}`}>{r.invoice_number ?? 'Draft invoice'}</Link> : r.expense_id ? <Link href={`/purchases/expenses/${r.expense_id}`}>{r.expense_number ?? 'Draft expense'}</Link> : <span>{r.message}</span>}</div>) : <div className="p-3 text-tx3">No generated occurrences.</div>}</Card>;
}
export function RecurringPage() {
  const { can } = useAuth(); const [edit, setEdit] = useState<Schedule | 'new' | null>(null); const [run, setRun] = useState<Schedule | null>(null);
  const [outcome, setOutcome] = useState<Run[] | null>(null);
  return <Screen eyebrow="Sales & Billing" title="Recurring billing" description="Generate due invoice drafts on demand or through the documented operating-system schedule. Automatic issuance requires explicit authority."
    actions={can('invoices.create') && <Button variant="primary" icon="add" onClick={() => setEdit('new')}>New recurring invoice</Button>}>
    {outcome && <Banner tone={outcome.some(r => r.status === 'failed') ? 'warn' : 'ok'}>{outcome.length} occurrence(s) processed. Existing successful occurrences are never generated twice.</Banner>}
    <ListPanel<Schedule> path="/billing/recurring/" columns={[
      { key: 'name', label: 'Schedule', render: s => <Primary title={s.name} sub={s.customer_name} /> }, { key: 'frequency', label: 'Frequency', render: s => `Every ${s.interval} ${s.frequency}` },
      { key: 'next', label: 'Next run', render: s => s.next_run_date ? formatDate(s.next_run_date) : '—' }, { key: 'auto', label: 'Issuance', render: s => s.auto_issue ? 'Authorized automatic' : 'Drafts for review' },
      { key: 'status', label: 'Status', render: s => <StatusBadge status={s.status} /> },
      { key: 'actions', label: '', render: s => <div className="flex gap-2"><Button size="xs" onClick={() => setEdit(s)}>{can('invoices.create') ? 'Edit / history' : 'View history'}</Button>{can('invoices.create') && <><Button size="xs" disabled={s.status !== 'active'} onClick={() => setRun(s)}>Run due</Button>{['active', 'paused'].includes(s.status) && <Button size="xs" onClick={() => void act(() => api.post(`/billing/recurring/${s.id}/status/`, { status: s.status === 'active' ? 'paused' : 'active' }), 'Schedule status saved').catch(e => toast(errorMessage(e), 'err'))}>{s.status === 'active' ? 'Pause' : 'Resume'}</Button>}</>}</div> },
    ]} />
    {edit && can('invoices.create') && <ScheduleDrawer schedule={edit === 'new' ? undefined : edit} onClose={() => setEdit(null)} />}
    {edit && !can('invoices.create') && <ReadonlyHistory id={edit === 'new' ? '' : String(edit.id)} onClose={() => setEdit(null)} />}
    <ConfirmDialog open={Boolean(run)} title={`Generate due occurrences for ${run?.name}?`} confirmLabel="Run due" onCancel={() => setRun(null)} onConfirm={async () => { const results = await act(() => api.post<Run[]>('/billing/recurring/run/', { until: today(), schedule_ids: [run!.id] }), 'Due run completed'); setOutcome(results); setRun(null); }}>Only occurrences due through today are processed. Review resulting drafts, approvals and any failures in the history.</ConfirmDialog>
  </Screen>;
}
function ReadonlyHistory({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useApi<Schedule>(`/billing/recurring/${id}/`);
  return <Card title={q.data?.name ?? 'Schedule history'} actions={<Button onClick={onClose}>Close history</Button>}><RunHistory runs={q.data?.runs} /></Card>;
}
