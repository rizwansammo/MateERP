'use client';
import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table';
import { InfoPanel } from '@/components/ui/InfoPanel';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { useAccounts, useConfig } from '@/features/accounting/shared';
import type { Bank } from '@/features/accounting/types';
import { FormDrawer, Screen, body, type FieldSpec } from '@/features/commerce/forms';
import { LinesEditor, Totals, blankLine, toEditLines, toPayload, useCalculation, postingAccounts, useTaxCodes } from '@/features/commerce/lines';
import { Activity, Card, DocumentBundle, LedgerImpact, ListPanel, Primary, StatusBadge, METHODS, act, today, useApi, useMoney } from '@/features/commerce/shared';
import type { Bill, Expense, Vendor, Project, FiledDocument } from '@/features/commerce/types';
import { FileViewer } from '@/features/commerce/FileViewer';
import { UploadDrawer } from '@/features/filing/UploadDrawer';
import { VendorPaymentDrawer } from './Payments';

export function BillDrawer({ bill, onClose }: { bill?: Bill; onClose: () => void }) {
  const config = useConfig(); const vendors = useApi<Page<Vendor>>('/purchasing/vendors/?status=active&page_size=100'); const projects = useApi<Page<Project>>('/sales/projects/?page_size=100');
  const initialLines = bill ? toEditLines(bill.lines, 'account_id') : [blankLine()]; const [lines, setLines] = useState(initialLines);
  const [currency, setCurrency] = useState(bill?.currency ?? config.data?.base_currency ?? ''); const [date, setDate] = useState(bill?.bill_date ?? today()); const [inclusive, setInclusive] = useState(bill?.prices_include_tax ?? false);
  const calc = useCalculation({ currency, date, lines, pricesIncludeTax: inclusive });
  return <FormDrawer title={bill ? `Edit ${bill.vendor_reference}` : 'New vendor bill'} eyebrow="Purchases & Expenses" width={1000} onClose={onClose}
    initial={{ vendor_id: String(bill?.vendor_id ?? ''), vendor_reference: bill?.vendor_reference ?? '', bill_date: date, due_date: bill?.due_date ?? today(), currency, prices_include_tax: inclusive, project_id: String(bill?.project_id ?? ''), notes: bill?.notes ?? '' }}
    extraDirty={JSON.stringify(lines) !== JSON.stringify(initialLines)} onValues={v => { setCurrency(String(v.currency)); setDate(String(v.bill_date)); setInclusive(Boolean(v.prices_include_tax)); }}
    fields={[
      { key: 'vendor_id', label: 'Vendor', type: 'select', required: true, options: [{ value: '', label: 'Select vendor…' }, ...(vendors.data?.results ?? []).map(v => ({ value: String(v.id), label: v.name }))] },
      { key: 'vendor_reference', label: 'Vendor invoice reference', required: true }, { key: 'bill_date', label: 'Bill date', type: 'date' }, { key: 'due_date', label: 'Due date', type: 'date' },
      { key: 'currency', label: 'Currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) },
      { key: 'project_id', label: 'Project (optional)', type: 'select', options: [{ value: '', label: 'None' }, ...(projects.data?.results ?? []).map(p => ({ value: String(p.id), label: p.name }))] },
      { key: 'prices_include_tax', label: 'Prices include tax', type: 'checkbox' }, { key: 'notes', label: 'Notes', type: 'textarea' },
    ]} onSave={v => { const data = { ...body(v), lines: toPayload(lines, 'account_id'), ...(bill ? { revision: bill.revision } : {}) }; return bill ? api.patch(`/purchasing/bills/${bill.id}/`, data) : api.post('/purchasing/bills/', data); }}>
    <div className="mt-4 border border-bd"><LinesEditor lines={lines} onChange={setLines} currency={currency} calc={calc.result} accountKind="expense" withItems={false} /><div className="flex flex-wrap justify-between gap-3 p-3"><Button size="sm" onClick={() => setLines(v => [...v, blankLine()])}>Add line</Button><Totals calc={calc.result} currency={currency} error={calc.error} /></div></div>
  </FormDrawer>;
}
export function useExpenseFields(): { fields: FieldSpec[] } {
  const vendors = useApi<Page<Vendor>>('/purchasing/vendors/?status=active&page_size=100'); const accounts = useAccounts(); const config = useConfig(); const banks = useApi<Page<Bank>>('/banking/accounts/?page_size=100'); const taxes = useTaxCodes(); const projects = useApi<Page<Project>>('/sales/projects/?page_size=100');
  return { fields: [
    { key: 'description', label: 'Description', required: true }, { key: 'vendor_id', label: 'Vendor', type: 'select', options: [{ value: '', label: 'No vendor' }, ...(vendors.data?.results ?? []).map(v => ({ value: String(v.id), label: v.name }))] },
    { key: 'amount', label: 'Amount', type: 'amount', required: true }, { key: 'currency', label: 'Currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) },
    { key: 'account_id', label: 'Expense account', type: 'select', options: [{ value: '', label: 'Company / vendor default' }, ...postingAccounts(accounts.data, 'expense').map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))] },
    { key: 'tax_code_id', label: 'Tax code', type: 'select', options: [{ value: '', label: 'No tax' }, ...(taxes.data?.results ?? []).map(t => ({ value: String(t.id), label: t.code }))] },
    { key: 'prices_include_tax', label: 'Amount includes tax', type: 'checkbox' }, { key: 'payment_mode', label: 'Funding', type: 'select', options: [{ value: 'accrued', label: 'Accrued — payable to vendor' }, { value: 'paid', label: 'Paid by company now' }] },
    { key: 'bank_account_id', label: 'Paying account', type: 'select', options: [{ value: '', label: 'None — accrued' }, ...(banks.data?.results ?? []).filter(b => b.is_active).map(b => ({ value: String(b.id), label: `${b.name} · ${b.currency}` }))] },
    { key: 'method', label: 'Payment method', type: 'select', options: METHODS }, { key: 'project_id', label: 'Project (optional)', type: 'select', options: [{ value: '', label: 'None' }, ...(projects.data?.results ?? []).map(p => ({ value: String(p.id), label: p.name }))] },
    { key: 'reference', label: 'Payment reference' }, { key: 'notes', label: 'Notes', type: 'textarea' },
  ] };
}
export function ExpenseDrawer({ expense, onClose }: { expense?: Expense; onClose: () => void }) {
  const config = useConfig(); const { fields } = useExpenseFields();
  return <FormDrawer title={expense ? `Edit ${expense.number ?? 'expense draft'}` : 'Record expense'} eyebrow="Purchases & Expenses" onClose={onClose}
    initial={{ description: expense?.description ?? '', vendor_id: String(expense?.vendor_id ?? ''), expense_date: expense?.expense_date ?? today(), due_date: expense?.due_date ?? '', currency: expense?.currency ?? config.data?.base_currency ?? '', amount: expense?.entered_amount ?? '', account_id: String(expense?.account_id ?? ''), tax_code_id: String(expense?.tax_code_id ?? ''), prices_include_tax: expense?.prices_include_tax ?? false, payment_mode: expense?.payment_mode ?? 'accrued', bank_account_id: String(expense?.bank_account_id ?? ''), method: expense?.method ?? 'bank_transfer', reference: expense?.reference ?? '', project_id: String(expense?.project_id ?? ''), notes: expense?.notes ?? '' }}
    fields={[{ key: 'expense_date', label: 'Expense date', type: 'date' }, { key: 'due_date', label: 'Due date (accrued)', type: 'date' }, ...fields]}
    onSave={v => { const data = { ...body(v), due_date: v.due_date || null, ...(expense ? { revision: expense.revision } : {}) }; return expense ? api.patch(`/purchasing/expenses/${expense.id}/`, data) : api.post('/purchasing/expenses/', data); }}>
    <Banner tone="info">Saving creates a draft. Posting records the company expense and its bank movement or vendor liability. Founder-paid expenses belong to Phase 5.</Banner>
  </FormDrawer>;
}
export function PayablesPage({ kind }: { kind: 'bills' | 'expenses' }) {
  const { can } = useAuth(); const money = useMoney(); const [create, setCreate] = useState(false); const bills = kind === 'bills';
  return <Screen eyebrow="Purchases & Expenses" title={bills ? 'Vendor bills' : 'Operating expenses'} description={bills ? 'Supplier invoices, approval, posted liabilities and settlement history.' : 'Company-funded operating costs, paid now or accrued for a vendor.'} actions={can(bills ? 'bills.manage' : 'expenses.manage') && <Button variant="primary" icon="add" onClick={() => setCreate(true)}>{bills ? 'New vendor bill' : 'Record expense'}</Button>}>
    <ListPanel<Bill | Expense> path={`/purchasing/${kind}/`} filters={[{ value: 'all', label: 'All' }, { value: 'draft', label: 'Drafts', query: 'status=draft' }, { value: 'approval', label: 'Awaiting approval', query: 'status=awaiting_approval' }, { value: 'posted', label: 'Posted', query: 'status=posted' }, { value: 'paid', label: 'Paid', query: 'status=paid' }, { value: 'void', label: 'Void', query: 'status=void' }]} columns={[
      { key: 'no', label: bills ? 'Bill' : 'Expense', render: p => <Primary href={`/purchases/${kind}/${p.id}`} mono title={p.number ?? 'Draft'} sub={'vendor_reference' in p ? p.vendor_reference : p.description} /> },
      { key: 'vendor', label: 'Vendor', render: p => p.vendor_name ?? '—' }, { key: 'date', label: 'Date', render: p => formatDate('bill_date' in p ? p.bill_date : p.expense_date) },
      { key: 'status', label: 'Status', render: p => <StatusBadge status={p.status} /> }, { key: 'total', label: 'Total', align: 'right', render: p => money(p.total, p.currency) }, { key: 'out', label: 'Outstanding', align: 'right', render: p => p.number ? money(p.outstanding, p.currency) : '—' },
    ]} />{create && (bills ? <BillDrawer onClose={() => setCreate(false)} /> : <ExpenseDrawer onClose={() => setCreate(false)} />)}
  </Screen>;
}
export function PayableDetail({ kind, id }: { kind: 'bills' | 'expenses'; id: string }) {
  const { can } = useAuth(); const money = useMoney(); const query = useApi<Bill | Expense>(`/purchasing/${kind}/${id}/`); const p = query.data;
  const [edit, setEdit] = useState(false); const [upload, setUpload] = useState(false); const [pay, setPay] = useState(false); const [decision, setDecision] = useState<'post' | 'void' | 'cancel' | null>(null); const [view, setView] = useState<FiledDocument | null>(null);
  const bills = kind === 'bills'; const canManage = can(bills ? 'bills.manage' : 'expenses.manage');
  return <Screen eyebrow={bills ? 'Vendor bill' : 'Operating expense'} title={p?.number ?? (p ? 'Draft' : 'Loading…')} description={p ? `${p.vendor_name ?? 'Company expense'} · ${'vendor_reference' in p ? p.vendor_reference : p.description}` : ''}
    actions={p && <>{p.status === 'draft' && canManage && <><Button onClick={() => setEdit(true)}>Edit draft</Button><Button variant="primary" onClick={() => setDecision('post')}>Post {bills ? 'bill' : 'expense'}</Button><Button variant="danger" onClick={() => setDecision('cancel')}>Cancel draft</Button></>}{['posted', 'partially_paid'].includes(p.status) && p.vendor_id && can('vendor_payments.manage') && <Button variant="primary" onClick={() => setPay(true)}>Pay vendor</Button>}{p.journal && p.status !== 'void' && canManage && <Button variant="danger" onClick={() => setDecision('void')}>Void</Button>}</>}>
    {Boolean(query.error) && <Banner tone="err">{errorMessage(query.error)}</Banner>}
    {p && <><InfoPanel title="Financial details" rows={[{ label: 'Status', value: <StatusBadge status={p.status} /> }, { label: 'Total', value: money(p.total, p.currency) }, { label: 'Tax', value: money(p.tax, p.currency) }, { label: 'Paid', value: money(p.amount_paid, p.currency) }, { label: 'Outstanding', value: p.number ? money(p.outstanding, p.currency) : 'Draft — no liability' }, { label: 'Date', value: formatDate('bill_date' in p ? p.bill_date : p.expense_date) }, { label: 'Approval', value: p.approval_id ? <Link href="/settings/approvals">Review request</Link> : 'Not pending' }]} />
      {'lines' in p && <Card title="Bill lines"><Table><THead><TR><TH>Description</TH><TH>Quantity</TH><TH align="right">Net</TH><TH align="right">Tax</TH><TH align="right">Total</TH></TR></THead><TBody>{p.lines.map((l, i) => <TR key={l.id ?? i}><TD>{l.description}</TD><TD>{l.quantity}</TD><TD align="right">{money(l.taxable, p.currency)}</TD><TD align="right">{money(l.tax, p.currency)}</TD><TD align="right">{money(l.total, p.currency)}</TD></TR>)}</TBody></Table></Card>}
      <LedgerImpact journals={[p.journal, p.void_journal]} empty="Drafts and pending approvals have no posted accounting impact." />
      <DocumentBundle query={`${bills ? 'bill' : 'expense'}=${p.id}&area=vendor`} empty="No supporting vendor files." onOpen={setView} actions={can('documents.manage') && <Button size="sm" onClick={() => setUpload(true)}>Upload evidence</Button>} />
      <Activity targetType={bills ? 'purchasing.vendorbill' : 'purchasing.expense'} targetId={p.id} />
      {edit && ('lines' in p ? <BillDrawer bill={p} onClose={() => setEdit(false)} /> : <ExpenseDrawer expense={p} onClose={() => setEdit(false)} />)}
      {pay && <VendorPaymentDrawer vendorId={p.vendor_id ?? undefined} target={{ kind, id: p.id, amount: p.outstanding }} onClose={() => setPay(false)} />}
      {upload && <UploadDrawer area="vendor" initial={{ kind: 'vendor_invoice', vendor_id: String(p.vendor_id ?? ''), [bills ? 'vendor_bill_id' : 'expense_id']: String(p.id) }} onClose={() => setUpload(false)} />}
    </>}
    <ConfirmDialog open={decision !== null} title={`${decision === 'post' ? 'Post' : decision === 'void' ? 'Void' : 'Cancel'} ${bills ? 'bill' : 'expense'}?`} confirmLabel={decision === 'post' ? 'Post' : decision === 'void' ? 'Void' : 'Cancel draft'} danger={decision !== 'post'} reason={decision === 'void' ? 'required' : undefined} onCancel={() => setDecision(null)} onConfirm={async reason => { const result = await act(() => api.post<Bill | Expense>(`/purchasing/${kind}/${id}/${decision}/`, decision === 'void' ? { reason } : {}), r => r.status === 'awaiting_approval' ? 'Submitted for approval — not posted' : `Record ${r.status}`); if (result.status === 'awaiting_approval') toast('Review the request in Approvals'); setDecision(null); }}>Posting uses the accounting engine and respects approval, period and reconciliation controls. Voiding retains the original record and creates a linked reversal.</ConfirmDialog>
    {view && <FileViewer doc={view} onClose={() => setView(null)} />}
  </Screen>;
}
