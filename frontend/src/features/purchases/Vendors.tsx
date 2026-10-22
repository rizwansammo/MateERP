'use client';
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Banner } from '@/components/ui/Banner';
import { InfoPanel } from '@/components/ui/InfoPanel';
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table';
import { api, errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { useAccounts, useConfig } from '@/features/accounting/shared';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { ListPanel, Primary, Card, useApi, useMoney } from '@/features/commerce/shared';
import { postingAccounts } from '@/features/commerce/lines';
import type { Vendor } from '@/features/commerce/types';

export function VendorDrawer({ vendor, onClose }: { vendor?: Vendor; onClose: () => void }) {
  const config = useConfig(); const accounts = useAccounts();
  return <FormDrawer title={vendor ? `Edit ${vendor.name}` : 'New vendor'} eyebrow="Purchases & Expenses" onClose={onClose}
    initial={{ name: vendor?.name ?? '', contact_name: vendor?.contact_name ?? '', email: vendor?.email ?? '', phone: vendor?.phone ?? '', address: vendor?.address ?? '', country: vendor?.country ?? '', currency: vendor?.currency ?? config.data?.base_currency ?? '', payment_terms_days: String(vendor?.payment_terms_days ?? 30), tax_id: vendor?.tax_id ?? '', website: vendor?.website ?? '', default_account_id: String(vendor?.default_account_id ?? ''), notes: vendor?.notes ?? '', is_active: vendor?.is_active ?? true }}
    fields={[
      { key: 'name', label: 'Vendor name', required: true }, { key: 'contact_name', label: 'Contact name' }, { key: 'email', label: 'Email', type: 'email' }, { key: 'phone', label: 'Phone' },
      { key: 'currency', label: 'Default currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) }, { key: 'payment_terms_days', label: 'Payment terms (days)', type: 'number' },
      { key: 'tax_id', label: 'Tax identification' }, { key: 'website', label: 'Website' }, { key: 'address', label: 'Address', type: 'textarea' }, { key: 'country', label: 'Country' },
      { key: 'default_account_id', label: 'Default expense account', type: 'select', options: [{ value: '', label: 'Use company default' }, ...postingAccounts(accounts.data, 'expense').map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))] },
      { key: 'notes', label: 'Notes', type: 'textarea' }, { key: 'is_active', label: 'Active', type: 'checkbox' },
    ]} onSave={v => vendor ? api.patch(`/purchasing/vendors/${vendor.id}/`, body(v, ['payment_terms_days'])) : api.post('/purchasing/vendors/', body(v, ['payment_terms_days']))} />;
}
export function VendorsPage() {
  const { can } = useAuth(); const money = useMoney(); const [create, setCreate] = useState(false);
  useEffect(() => { const timer = window.setTimeout(() => { if (new URLSearchParams(window.location.search).get('new') === '1' && can('vendors.manage')) setCreate(true); }, 0); return () => window.clearTimeout(timer); }, [can]);
  return <Screen eyebrow="Purchases & Expenses" title="Vendors & suppliers" description="Supplier identities, payment terms and outstanding company obligations." actions={can('vendors.manage') && <Button variant="primary" icon="add" onClick={() => setCreate(true)}>New vendor</Button>}>
    <ListPanel<Vendor> path="/purchasing/vendors/" search="Search vendors…" filters={[{ value: 'all', label: 'All' }, { value: 'active', label: 'Active', query: 'status=active' }, { value: 'inactive', label: 'Inactive', query: 'status=inactive' }]} columns={[
      { key: 'name', label: 'Vendor', render: v => <Primary href={`/purchases/vendors/${v.id}`} title={v.name} sub={`${v.code} · ${v.contact_name || v.email}`} /> },
      { key: 'currency', label: 'Currency', render: v => v.currency }, { key: 'terms', label: 'Terms', render: v => `Net ${v.payment_terms_days}` },
      { key: 'balance', label: 'Payable', align: 'right', render: v => Object.entries(v.balances ?? {}).map(([c, a]) => <div key={c}>{money(a, c)}</div>) }, { key: 'status', label: 'Status', render: v => v.is_active ? 'Active' : 'Inactive' },
    ]} />{create && <VendorDrawer onClose={() => setCreate(false)} />}
  </Screen>;
}
interface StatementRow { date: string; currency: string; kind: string; number: string; debit: string; credit: string; balance: string }
export function VendorDetail({ id }: { id: string }) {
  const { can } = useAuth(); const money = useMoney(); const [edit, setEdit] = useState(false);
  const query = useApi<Vendor>(`/purchasing/vendors/${id}/`); const statement = useApi<StatementRow[]>(`/purchasing/vendors/${id}/statement/`); const v = query.data;
  return <Screen eyebrow="Vendor" title={v?.name ?? 'Vendor'} description={v ? `${v.code} · ${v.email} · Net ${v.payment_terms_days}` : ''} actions={v && can('vendors.manage') && <Button onClick={() => setEdit(true)}>Edit vendor</Button>}>
    {Boolean(query.error || statement.error) && <Banner tone="err">{errorMessage(query.error || statement.error)}</Banner>}
    {v && <InfoPanel title="Supplier details" rows={[{ label: 'Contact', value: v.contact_name || '—' }, { label: 'Address', value: v.address || '—' }, { label: 'Phone', value: v.phone || '—' }, { label: 'Status', value: v.is_active ? 'Active' : 'Inactive' }, ...Object.entries(v.balances ?? {}).map(([c, a]) => ({ label: `Payable · ${c}`, value: money(a, c) }))]} />}
    <Card title="Vendor statement" subtitle="Bills, accrued expenses, payments and traceable reversals"><Table><THead><TR><TH>Date</TH><TH>Document</TH><TH>Type</TH><TH align="right">Debit</TH><TH align="right">Credit</TH><TH align="right">Payable balance</TH></TR></THead><TBody>{statement.data?.map((r, i) => <TR key={i}><TD>{formatDate(r.date)}</TD><TD>{r.number}</TD><TD>{r.kind}</TD><TD align="right">{money(r.debit, r.currency)}</TD><TD align="right">{money(r.credit, r.currency)}</TD><TD align="right">{money(r.balance, r.currency)}</TD></TR>)}{statement.data?.length === 0 && <TR><TD colSpan={6}>No posted vendor history.</TD></TR>}</TBody></Table></Card>
    {edit && v && <VendorDrawer vendor={v} onClose={() => setEdit(false)} />}
  </Screen>;
}
