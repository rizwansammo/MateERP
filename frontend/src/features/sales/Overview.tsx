'use client';
import Link from 'next/link';
import { Banner } from '@/components/ui/Banner';
import { StatGrid } from '@/components/ui/StatGrid';
import { Screen } from '@/features/commerce/forms';
import { Card, useApi, useMoney } from '@/features/commerce/shared';
import type { Reconciled } from '@/features/commerce/types';
import { errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { linkClass } from '@/features/accounting/shared';
import { InvoiceTable } from './tables';
import { MonthlyChart, BreakdownChart, type MonthlyPoint, type Breakdown } from '@/features/commerce/Charts';

export interface SalesOverview {
  base_currency: string; outstanding: string; overdue: string; overdue_count: number; open_count: number;
  invoiced_this_month: string; collected_this_month: string; pending_verification: number; drafts: number;
  series: MonthlyPoint[]; aging: Breakdown[]; series_from: string;
}
export function OverviewPage() {
  const { can } = useAuth();
  const query = useApi<SalesOverview>('/billing/overview/');
  const checks = useApi<Record<string, Reconciled>>('/billing/reconciliation/');
  const money = useMoney();
  const d = query.data;
  return <Screen eyebrow="Sales & Billing" title="Sales overview" description="Billing, verified collections and receivables from the company's financial records."
    actions={<><Link className={linkClass} href="/sales/setup">Sales & purchases setup</Link>{can('invoices.create') && <Link className={linkClass} href="/sales/invoices/new">+ Create invoice</Link>}<Link className={linkClass} href="/sales/payments">Payments</Link></>}>
    {Boolean(query.error) && <Banner tone="err">{errorMessage(query.error)}</Banner>}
    <StatGrid minWidth={180} stats={[
      { label: 'Invoiced this month', value: d ? money(d.invoiced_this_month, d.base_currency) : '—', accentBar: true },
      { label: 'Collected this month', value: d ? money(d.collected_this_month, d.base_currency) : '—', sub: 'Verified payments', accentBar: true },
      { label: 'Outstanding receivables', value: d ? money(d.outstanding, d.base_currency) : '—', sub: d ? `${d.open_count} open invoices` : '', accentBar: true },
      { label: 'Overdue', value: d ? money(d.overdue, d.base_currency) : '—', sub: d ? `${d.overdue_count} invoices` : '', tone: 'warn' },
      { label: 'Pending verification', value: d?.pending_verification ?? '—', accentBar: true },
      { label: 'Drafts & approvals', value: d?.drafts ?? '—', accentBar: true },
    ]} />
    <div className="grid items-start gap-[18px] xl:grid-cols-2"><MonthlyChart title="Invoiced vs collected" subtitle={`Fiscal year to date · ${d?.base_currency ?? 'base currency'}`} points={d?.series} series={[{ key: 'invoiced', label: 'Invoiced' }, { key: 'collected', label: 'Collected' }]} currency={d?.base_currency} /><BreakdownChart aging title="Receivables aging" subtitle="Outstanding invoice balances · historical base book value" rows={d?.aging} currency={d?.base_currency} /></div>
    <Card title="Ledger reconciliation" subtitle="Receivables and customer credit controls · base currency">
      {checks.data ? Object.entries(checks.data).map(([name, c]) => <div key={name} className="flex flex-wrap justify-between gap-3 border-b border-bd px-4 py-3 text-[12.5px] last:border-0"><span className="font-semibold capitalize">{name.replaceAll('_', ' ')}</span><span>Subledger {money(c.subledger)} · General ledger {money(c.ledger)} · Difference {money(c.difference)}</span></div>)
        : <div className="p-4 text-tx3">{checks.error ? errorMessage(checks.error) : 'Loading reconciliation…'}</div>}
    </Card>
    <InvoiceTable title="Open invoices" status="open" />
  </Screen>;
}

