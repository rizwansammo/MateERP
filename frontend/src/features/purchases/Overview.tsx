'use client';
import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { StatGrid } from '@/components/ui/StatGrid';
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table';
import { Input, Select } from '@/components/ui/Input';
import { errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { Screen } from '@/features/commerce/forms';
import { Card, StatusBadge, useApi, useMoney } from '@/features/commerce/shared';
import type { Reconciled } from '@/features/commerce/types';
import { linkClass } from '@/features/accounting/shared';
import { BillDrawer, ExpenseDrawer } from './Payables';
import { VendorPaymentDrawer } from './Payments';
import { MonthlyChart, BreakdownChart, type MonthlyPoint, type Breakdown } from '@/features/commerce/Charts';

interface Overview { base_currency: string; payables: string; spend_this_month: string; open_bills: number; overdue_bills: number; drafts: number; awaiting_approval: number; upcoming_renewals: number; series: MonthlyPoint[]; categories: Breakdown[]; top_vendors: Breakdown[]; expense_series: {key: string; label: string}[] }
export function OverviewPage() {
  const query = useApi<Overview>('/purchasing/overview/'); const check = useApi<Reconciled>('/purchasing/reconciliation/'); const money = useMoney(); const { can } = useAuth(); const [drawer, setDrawer] = useState<'bill' | 'expense' | 'pay' | null>(null); const d = query.data;
  return <Screen eyebrow="Purchases & Expenses" title="Purchases overview" description="Operating spend, supplier liabilities and upcoming renewals from posted company records." actions={<><Link className={linkClass} href="/sales/setup">Posting setup</Link>{can('vendor_payments.manage') && <Button onClick={() => setDrawer('pay')}>Pay vendor</Button>}{can('bills.manage') && <Button onClick={() => setDrawer('bill')}>New vendor bill</Button>}{can('expenses.manage') && <Button variant="primary" icon="add" onClick={() => setDrawer('expense')}>Record expense</Button>}</>}>
    {Boolean(query.error) && <Banner tone="err">{errorMessage(query.error)}</Banner>}
    <StatGrid minWidth={180} stats={[
      { label: 'Spend this month', value: d ? money(d.spend_this_month, d.base_currency) : '—', accentBar: true }, { label: 'Accounts payable', value: d ? money(d.payables, d.base_currency) : '—', accentBar: true }, { label: 'Open bills', value: d?.open_bills ?? '—', accentBar: true }, { label: 'Overdue bills', value: d?.overdue_bills ?? '—', tone: 'warn' }, { label: 'Awaiting approval', value: d?.awaiting_approval ?? '—', accentBar: true }, { label: 'Upcoming renewals', value: d?.upcoming_renewals ?? '—', accentBar: true },
    ]} />
    <div className="grid items-start gap-[18px] xl:grid-cols-2"><MonthlyChart stacked title="Monthly spend by category" subtitle="Fiscal year to date · expense accounts, excluding recoverable tax and capital items" points={d?.series} series={d?.expense_series ?? []} currency={d?.base_currency} /><BreakdownChart title="Top vendors" subtitle="Fiscal year · posted expense costs at historical base values" rows={d?.top_vendors} currency={d?.base_currency} /></div>
    <Card title="Payables reconciliation"><div className="p-4 text-[12.5px]">{check.data ? <>Subledger {money(check.data.subledger)} · General ledger {money(check.data.ledger)} · Difference {money(check.data.difference)}</> : check.error ? errorMessage(check.error) : 'Loading…'}</div></Card>
    <PurchaseHistory embedded />
    {drawer === 'bill' && <BillDrawer onClose={() => setDrawer(null)} />}{drawer === 'expense' && <ExpenseDrawer onClose={() => setDrawer(null)} />}{drawer === 'pay' && <VendorPaymentDrawer onClose={() => setDrawer(null)} />}
  </Screen>;
}
interface HistoryRow { id: number; kind: string; date: string; number: string; reference: string; party: string; status: string; currency: string; amount: string }
export function PurchaseHistory({ embedded = false }: { embedded?: boolean }) {
  const query = useApi<HistoryRow[]>('/purchasing/history/?limit=500'); const money = useMoney(); const [search, setSearch] = useState(''); const [kind, setKind] = useState('all');
  const rows = (query.data ?? []).filter(r => (kind === 'all' || r.kind === kind) && `${r.number} ${r.reference} ${r.party}`.toLowerCase().includes(search.toLowerCase()));
  const content = <Card title={embedded ? 'Recent purchase activity' : 'Purchase history'} subtitle="Latest 500 bills, expenses and vendor payments" actions={<div className="flex gap-2"><Input aria-label="Search purchase history" placeholder="Search history…" value={search} onChange={e => setSearch(e.target.value)} /><Select aria-label="History type" value={kind} onChange={e => setKind(e.target.value)}>{['all', 'Vendor bill', 'Expense', 'Vendor payment'].map(v => <option key={v} value={v}>{v === 'all' ? 'All activity' : v}</option>)}</Select></div>}>
    {Boolean(query.error) && <Banner tone="err">{errorMessage(query.error)}</Banner>}
    <Table><THead><TR><TH>Date</TH><TH>Document</TH><TH>Vendor</TH><TH>Type / reference</TH><TH>Status</TH><TH align="right">Amount</TH></TR></THead><TBody>{rows.slice(0, embedded ? 12 : 500).map(r => <TR key={`${r.kind}/${r.id}`}><TD>{formatDate(r.date)}</TD><TD><Link href={`/purchases/${r.kind === 'Vendor bill' ? 'bills' : r.kind === 'Expense' ? 'expenses' : 'payments'}/${r.id}`}>{r.number}</Link></TD><TD>{r.party || '—'}</TD><TD>{r.kind}<div className="text-tx3">{r.reference}</div></TD><TD><StatusBadge status={r.status} /></TD><TD align="right">{money(r.amount, r.currency)}</TD></TR>)}{!rows.length && <TR><TD colSpan={6}>{query.loading ? 'Loading purchase activity…' : 'No matching purchase activity.'}</TD></TR>}</TBody></Table>
  </Card>;
  return embedded ? content : <Screen eyebrow="Purchases & Expenses" title="Purchase history" description="Company purchasing activity and settlement records." actions={<Link className={linkClass} href="/purchases/payments">Vendor payments</Link>}>{content}</Screen>;
}


