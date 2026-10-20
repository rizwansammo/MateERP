'use client';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { Drawer } from '@/components/ui/Overlay';
import { useConfig } from '@/features/accounting/shared';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { ListPanel, Primary, StatusBadge, act, today, useApi } from '@/features/commerce/shared';
import type { ExpenseSchedule, Run } from '@/features/commerce/types';
import { FREQUENCIES, RunHistory } from '@/features/sales/Recurring';
import { useExpenseFields } from './Payables';

function ScheduleDrawer({ schedule, onClose }: { schedule?: ExpenseSchedule; onClose: () => void }) {
  const config = useConfig(); const { fields } = useExpenseFields(); const template = schedule?.template ?? {};
  return <FormDrawer title={schedule ? `Edit ${schedule.name}` : 'New recurring expense'} eyebrow="Purchases & Expenses" onClose={onClose}
    initial={{ name: schedule?.name ?? '', vendor_id: String(schedule?.vendor_id ?? ''), currency: schedule?.currency ?? config.data?.base_currency ?? '', frequency: schedule?.frequency ?? 'monthly', interval: String(schedule?.interval ?? 1), start_date: schedule?.start_date ?? today(), end_date: schedule?.end_date ?? '', reminder_days: String(schedule?.reminder_days ?? 7), description: String(template.description ?? ''), account_id: String(template.account_id ?? ''), amount: String(template.amount ?? ''), tax_code_id: String(template.tax_code_id ?? ''), prices_include_tax: Boolean(template.prices_include_tax), payment_mode: String(template.payment_mode ?? 'accrued'), bank_account_id: String(template.bank_account_id ?? ''), method: String(template.method ?? 'bank_transfer'), project_id: String(template.project_id ?? ''), reference: '', notes: String(template.notes ?? '') }}
    fields={[
      { key: 'name', label: 'Schedule name', required: true }, { key: 'frequency', label: 'Frequency', type: 'select', options: FREQUENCIES }, { key: 'interval', label: 'Every (interval)', type: 'number' }, { key: 'start_date', label: 'Start date', type: 'date' }, { key: 'end_date', label: 'End date (optional)', type: 'date' }, { key: 'reminder_days', label: 'Reminder days', type: 'number' }, ...fields.filter(f => f.key !== 'reference'),
    ]} onSave={v => { const data = { ...body(v, ['interval', 'reminder_days']), end_date: v.end_date || null, ...(schedule ? { revision: schedule.revision } : {}) }; return schedule ? api.patch(`/purchasing/recurring/${schedule.id}/`, data) : api.post('/purchasing/recurring/', data); }}>
    <Banner tone="info">Due runs create draft expenses only. Review and post each expense through the normal approval workflow.</Banner>
  </FormDrawer>;
}
function History({ schedule, onClose }: { schedule: ExpenseSchedule; onClose: () => void }) {
  const q = useApi<ExpenseSchedule>(`/purchasing/recurring/${schedule.id}/`);
  return <Drawer open title={schedule.name} eyebrow="Recurring expense history" onClose={onClose}><RunHistory runs={q.data?.runs} /></Drawer>;
}
export function RecurringExpensesPage() {
  const { can } = useAuth(); const [edit, setEdit] = useState<ExpenseSchedule | 'new' | null>(null); const [history, setHistory] = useState<ExpenseSchedule | null>(null); const [run, setRun] = useState<ExpenseSchedule | null>(null); const [result, setResult] = useState<Run[] | null>(null);
  return <Screen eyebrow="Purchases & Expenses" title="Recurring expenses" description="Subscriptions and recurring operating costs. Due occurrences produce persistent drafts, never duplicate company expenses." actions={can('expenses.manage') && <Button variant="primary" icon="add" onClick={() => setEdit('new')}>New recurring expense</Button>}>
    {result && <Banner tone={result.some(r => r.status === 'failed') ? 'warn' : 'ok'}>{result.length} due occurrence(s) processed. Check history for drafts and any failures.</Banner>}
    <ListPanel<ExpenseSchedule> path="/purchasing/recurring/" columns={[
      { key: 'name', label: 'Schedule', render: s => <Primary title={s.name} sub={s.vendor_name} /> }, { key: 'frequency', label: 'Frequency', render: s => `Every ${s.interval} ${s.frequency}` }, { key: 'next', label: 'Next run', render: s => s.next_run_date ? formatDate(s.next_run_date) : '—' }, { key: 'status', label: 'Status', render: s => <StatusBadge status={s.status} /> },
      { key: 'actions', label: '', render: s => <div className="flex gap-2"><Button size="xs" onClick={() => setHistory(s)}>History</Button>{can('expenses.manage') && <><Button size="xs" disabled={!['active', 'paused'].includes(s.status)} onClick={() => setEdit(s)}>Edit</Button><Button size="xs" disabled={s.status !== 'active'} onClick={() => setRun(s)}>Run due</Button>{['active', 'paused'].includes(s.status) && <Button size="xs" onClick={() => void act(() => api.post(`/purchasing/recurring/${s.id}/status/`, { status: s.status === 'active' ? 'paused' : 'active' }), 'Schedule updated').catch(e => toast(errorMessage(e), 'err'))}>{s.status === 'active' ? 'Pause' : 'Resume'}</Button>}</>}</div> },
    ]} />
    {edit && <ScheduleDrawer schedule={edit === 'new' ? undefined : edit} onClose={() => setEdit(null)} />}{history && <History schedule={history} onClose={() => setHistory(null)} />}
    <ConfirmDialog open={Boolean(run)} title={`Run due expenses for ${run?.name}?`} confirmLabel="Run due" onCancel={() => setRun(null)} onConfirm={async () => { setResult(await act(() => api.post<Run[]>('/purchasing/recurring/run/', { until: today(), schedule_ids: [run!.id] }), 'Due run completed')); setRun(null); }}>Generate due draft expenses through today. Previously successful occurrences will not be duplicated.</ConfirmDialog>
  </Screen>;
}
