'use client';
import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { useAuth } from '@/lib/auth/AuthProvider';
import { api, errorMessage } from '@/lib/api/client';
import { useAccounts, useConfig } from '@/features/accounting/shared';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { Card, ListPanel, Primary, useApi, useMoney } from '@/features/commerce/shared';
import { useTaxCodes, postingAccounts } from '@/features/commerce/lines';
import type { BillingItem } from '@/features/commerce/types';

interface Settings { default_revenue_account_id: number | null; default_expense_account_id: number | null; controls: Record<string, { id: number; code: string; name: string } | null> }
export function SetupPage() {
  const { can } = useAuth(); const accounts = useAccounts(); const config = useConfig(); const taxes = useTaxCodes(); const money = useMoney();
  const settings = useApi<Settings>('/billing/settings/'); const [edit, setEdit] = useState(false); const [item, setItem] = useState<BillingItem | 'new' | null>(null);
  const opts = (kind: 'revenue' | 'expense') => [{ value: '', label: 'Select…' }, ...postingAccounts(accounts.data, kind).map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))];
  return <Screen eyebrow="Settings" title="Sales & purchases setup" description="Shared posting defaults and a reusable billing catalog. Financial control accounts are configured in the chart of accounts.">
    {Boolean(settings.error) && <Banner tone="err">{errorMessage(settings.error)}</Banner>}
    <Card title="Posting defaults" actions={can('accounting.manage') && <Button size="sm" onClick={() => setEdit(true)}>Edit defaults</Button>}>
      <div className="grid gap-3 p-4 sm:grid-cols-2">{settings.data && ['default_revenue_account_id', 'default_expense_account_id'].map(k => { const id = k === 'default_revenue_account_id' ? settings.data!.default_revenue_account_id : settings.data!.default_expense_account_id; const a = accounts.data?.find(a => a.id === id); return <div key={k}><span className="text-tx3">{k.startsWith('default_revenue') ? 'Revenue' : 'Expense'}</span><div>{a ? `${a.code} · ${a.name}` : 'Not configured'}</div></div>; })}</div>
      <div className="border-t border-bd p-4 text-[12px]">{Object.entries(settings.data?.controls ?? {}).map(([k, a]) => <div key={k} className="mb-1 flex justify-between"><span>{k.replace('_', ' ')}</span><span>{a ? `${a.code} · ${a.name}` : 'Not configured'}</span></div>)}<Link href="/banking/coa">Manage chart of accounts</Link> · <Link href="/settings/branding">Publish document branding</Link></div>
    </Card>
    <ListPanel<BillingItem> path="/sales/items/" title="Billing items" actions={can('sales.manage') && <Button size="sm" onClick={() => setItem('new')}>New billing item</Button>} columns={[
      { key: 'name', label: 'Item', render: i => <Primary title={i.name} sub={i.code} /> }, { key: 'unit', label: 'Unit', render: i => i.unit }, { key: 'price', label: 'Unit price', align: 'right', render: i => money(i.unit_price, i.currency) },
      { key: 'active', label: 'Status', render: i => i.is_active ? 'Active' : 'Inactive' }, { key: 'edit', label: '', render: i => can('sales.manage') && <Button size="xs" onClick={() => setItem(i)}>Edit</Button> },
    ]} />
    {edit && settings.data && <FormDrawer title="Posting defaults" eyebrow="Setup" initial={{ default_revenue_account_id: String(settings.data.default_revenue_account_id ?? ''), default_expense_account_id: String(settings.data.default_expense_account_id ?? '') }} fields={[
      { key: 'default_revenue_account_id', label: 'Default revenue account', type: 'select', options: opts('revenue') }, { key: 'default_expense_account_id', label: 'Default expense account', type: 'select', options: opts('expense') },
    ]} onSave={v => api.put('/billing/settings/', body(v))} onClose={() => setEdit(false)} />}
    {item && <FormDrawer title={item === 'new' ? 'New billing item' : 'Edit billing item'} eyebrow="Billing catalog" onClose={() => setItem(null)} initial={item === 'new' ? { name: '', code: '', description: '', unit: 'service', unit_price: '', currency: config.data?.base_currency ?? '', revenue_account_id: '', tax_code_id: '', is_active: true } : { name: item.name, code: item.code, description: item.description, unit: item.unit, unit_price: item.unit_price, currency: item.currency, revenue_account_id: String(item.revenue_account_id ?? ''), tax_code_id: String(item.tax_code_id ?? ''), is_active: item.is_active }} fields={[
      { key: 'name', label: 'Item name', required: true }, { key: 'code', label: 'Item code', required: true }, { key: 'description', label: 'Description' }, { key: 'unit', label: 'Unit' }, { key: 'unit_price', label: 'Unit price', type: 'amount' },
      { key: 'currency', label: 'Currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) }, { key: 'revenue_account_id', label: 'Revenue account', type: 'select', options: opts('revenue') },
      { key: 'tax_code_id', label: 'Tax code', type: 'select', options: [{ value: '', label: 'No tax' }, ...(taxes.data?.results ?? []).map(t => ({ value: String(t.id), label: t.code }))] }, { key: 'is_active', label: 'Active', type: 'checkbox' },
    ]} onSave={v => item === 'new' ? api.post('/sales/items/', body(v)) : api.patch(`/sales/items/${item.id}/`, body(v))} />}
  </Screen>;
}
