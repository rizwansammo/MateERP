'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Input, AmountInput } from '@/components/ui/Input';
import { StatGrid } from '@/components/ui/StatGrid';
import { Table, THead, TBody, TH, TD, TR } from '@/components/ui/Table';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useConfig } from '@/features/accounting/shared';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { Card, ListPanel, Primary, StatusBadge, act, useApi, useMoney } from '@/features/commerce/shared';
import type { Customer, Invoice, Project } from '@/features/commerce/types';
import { InvoiceTable } from './tables';

export function ProjectDrawer({ project, onClose }: { project?: Project; onClose: () => void }) {
  const config = useConfig();
  const customers = useApi<Page<Customer>>('/sales/customers/?page_size=100');
  const initialMilestones = (project?.milestones ?? []).map(m => ({ name: m.name, percent: m.percent }));
  const [milestones, setMilestones] = useState(initialMilestones);
  return <FormDrawer title={project ? `Edit ${project.reference}` : 'New project'} eyebrow="Project financials" onClose={onClose}
    initial={{ name: project?.name ?? '', reference: project?.reference ?? '', customer_id: String(project?.customer_id ?? ''), currency: project?.currency ?? config.data?.base_currency ?? '', contract_value: project?.contract_value ?? '', status: project?.status ?? 'active', notes: project?.notes ?? '' }}
    extraDirty={JSON.stringify(milestones) !== JSON.stringify(initialMilestones)} fields={[
      { key: 'name', label: 'Project name', required: true }, { key: 'reference', label: 'Project reference', required: true },
      { key: 'customer_id', label: 'Customer', type: 'select', options: [{ value: '', label: 'Select customer…' }, ...(customers.data?.results ?? []).map(c => ({ value: String(c.id), label: c.name }))] },
      { key: 'currency', label: 'Currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(c => ({ value: c, label: c })) },
      { key: 'contract_value', label: 'Contract value', type: 'amount' },
      { key: 'status', label: 'Status', type: 'select', options: ['active', 'on_hold', 'completed', 'cancelled'].map(s => ({ value: s, label: s.replace('_', ' ') })) },
      { key: 'notes', label: 'Notes', type: 'textarea' },
    ]} onSave={values => {
      const data = { ...body(values), ...(project && JSON.stringify(milestones) === JSON.stringify(initialMilestones) ? {} : { milestones }) };
      return project ? api.patch(`/sales/projects/${project.id}/`, data) : api.post('/sales/projects/', data);
    }}>
    <div className="mt-4 border border-bd p-3"><div className="mb-3 text-[13px] font-semibold">Billing milestones</div>
      {milestones.map((m, i) => <div key={i} className="mb-2 flex gap-2"><Input aria-label={`Milestone ${i + 1} name`} placeholder="Milestone name" value={m.name} onChange={e => setMilestones(v => v.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} /><AmountInput aria-label={`Milestone ${i + 1} percent`} placeholder="Percent" value={m.percent} onChange={e => setMilestones(v => v.map((x, j) => j === i ? { ...x, percent: e.target.value } : x))} /><Button size="sm" aria-label={`Remove milestone ${i + 1}`} onClick={() => setMilestones(v => v.filter((_, j) => i !== j))}>Remove</Button></div>)}
      <Button size="sm" icon="add" onClick={() => setMilestones(v => [...v, { name: '', percent: '' }])}>Add milestone</Button>
      <p className="mt-2 text-[12px] text-tx3">Milestones must total 100%. Issued billing preserves the original milestone details.</p>
    </div>
  </FormDrawer>;
}
export function ProjectsPage() {
  const { can } = useAuth(); const money = useMoney(); const [editing, setEditing] = useState(false);
  return <Screen eyebrow="Sales & Billing" title="Project financials" description="Contracts, milestone billing, collections and posted project costs." actions={can('sales.manage') && <Button variant="primary" icon="add" onClick={() => setEditing(true)}>New project</Button>}>
    <ListPanel<Project> path="/sales/projects/" columns={[
      { key: 'ref', label: 'Project', render: p => <Primary href={`/sales/projects/${p.id}`} title={p.name} sub={p.reference} /> },
      { key: 'customer', label: 'Customer', render: p => p.customer_name }, { key: 'status', label: 'Status', render: p => <StatusBadge status={p.status} /> },
      { key: 'value', label: 'Contract value', align: 'right', render: p => money(p.contract_value, p.currency) }, { key: 'milestones', label: 'Milestones', render: p => p.milestones.length },
    ]} />{editing && <ProjectDrawer onClose={() => setEditing(false)} />}
  </Screen>;
}
interface Financials { currency: string; contract_value: string; invoiced: string; collected: string; outstanding: string; uninvoiced: string; costs: string; margin: string;
  base_currency: string; base_revenue: string; base_costs: string; base_margin: string; note: string;
  milestones: { id: number; name: string; percent: string; amount: string; invoice: { id: number; number: string | null; status: string } | null }[];
  cost_lines: { kind: string; id: number; number: string; amount: string; currency: string; base_amount: string; date: string; party: string }[]; }
export function ProjectDetail({ id }: { id: string }) {
  const { can } = useAuth(); const router = useRouter(); const money = useMoney(); const [edit, setEdit] = useState(false); const [busy, setBusy] = useState(false);
  const project = useApi<Project>(`/sales/projects/${id}/`); const financials = useApi<Financials>(`/billing/projects/${id}/financials/`); const p = project.data; const f = financials.data;
  const bill = async (milestoneId: number) => { setBusy(true); try { const inv = await act(() => api.post<Invoice>('/billing/invoices/from-source/', { milestone_id: milestoneId }), 'Milestone invoice draft created'); router.push(`/sales/invoices/${inv.id}/edit`); } catch(e) { toast(errorMessage(e), 'err'); } finally { setBusy(false); } };
  return <Screen eyebrow="Project financials" title={p?.name ?? 'Project'} description={p?.reference} actions={p && can('sales.manage') && <Button onClick={() => setEdit(true)}>Edit project</Button>}>
    {Boolean(project.error || financials.error) && <Banner tone="err">{errorMessage(project.error || financials.error)}</Banner>}
    {f && <><StatGrid minWidth={160} stats={(['contract_value', 'invoiced', 'collected', 'outstanding'] as const).map(k => ({ label: k.replace('_', ' '), value: money(f[k], f.currency), accentBar: true }))} /><StatGrid minWidth={180} stats={([{ label: 'Net posted revenue', value: f.base_revenue }, { label: 'Posted project costs', value: f.base_costs }, { label: 'Posted margin', value: f.base_margin }]).map(s => ({ label: `${s.label} · ${f.base_currency}`, value: money(s.value, f.base_currency), accentBar: true }))} /><p className="text-[12px] text-tx3">{f.note}</p></>}
    <Card title="Milestone billing"><Table><THead><TR><TH>Milestone</TH><TH>Share</TH><TH align="right">Amount</TH><TH>Invoice</TH></TR></THead><TBody>{f?.milestones.map(m => <TR key={m.id}><TD>{m.name}</TD><TD>{m.percent}%</TD><TD align="right">{money(m.amount, f.currency)}</TD><TD>{m.invoice ? <Link href={`/sales/invoices/${m.invoice.id}`}>{m.invoice.number ?? 'Draft'} · {m.invoice.status}</Link> : can('invoices.create') ? <Button size="xs" disabled={busy} onClick={() => void bill(m.id)}>Create invoice</Button> : 'Unbilled'}</TD></TR>)}{f?.milestones.length === 0 && <TR><TD colSpan={4}>No milestones configured.</TD></TR>}</TBody></Table></Card>
    <InvoiceTable projectId={Number(id)} title="Project invoices" />
    <Card title="Posted project costs"><Table><THead><TR><TH>Record</TH><TH>Date</TH><TH>Vendor</TH><TH align="right">Expense amount</TH><TH align="right">Historical base cost</TH></TR></THead><TBody>{f?.cost_lines.map(c => <TR key={`${c.kind}-${c.id}`}><TD><Link className="text-pr" href={`/purchases/${c.kind === 'Expense' ? 'expenses' : 'bills'}/${c.id}`}>{c.number}</Link></TD><TD>{c.date}</TD><TD>{c.party || '—'}</TD><TD align="right">{money(c.amount, c.currency)}</TD><TD align="right">{money(c.base_amount, f.base_currency)}</TD></TR>)}{f?.cost_lines.length === 0 && <TR><TD colSpan={5}>No posted project costs.</TD></TR>}</TBody></Table></Card>
    {edit && p && <ProjectDrawer project={p} onClose={() => setEdit(false)} />}
  </Screen>;
}
