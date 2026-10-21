'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { InfoPanel } from '@/components/ui/InfoPanel';
import { useAccounts, useConfig } from '@/features/accounting/shared';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { postingAccounts, useTaxCodes } from '@/features/commerce/lines';
import { Card, Gate, ListPanel, Primary, StatusBadge, today, useApi, useMoney } from '@/features/commerce/shared';
import type { Vendor } from '@/features/commerce/types';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import type { CatalogItem, PriceRevision, Reference } from './types';

function ReferenceDrawer({ kind, onClose }: { kind: 'units' | 'categories'; onClose: () => void }) {
  return <FormDrawer title={kind === 'units' ? 'New unit of measure' : 'New category'} eyebrow="Catalog setup"
    width={480} onClose={onClose} initial={{ code: '', name: '', allows_fraction: true }}
    fields={[{ key: 'code', label: 'Code', required: true }, { key: 'name', label: 'Name', required: true },
      ...(kind === 'units' ? [{ key: 'allows_fraction', label: 'Allow fractional quantities', type: 'checkbox' as const }] : [])]}
    onSave={v => api.post(`/catalog/${kind}/`, body(v))} />;
}

export function ItemDrawer({ item, service, onClose }: { item?: CatalogItem; service: boolean; onClose: () => void }) {
  const units = useApi<Page<Reference>>('/catalog/units/?page_size=100');
  const categories = useApi<Page<Reference>>('/catalog/categories/?page_size=100');
  const vendors = useApi<Page<Vendor>>('/purchasing/vendors/?page_size=100&status=active');
  const accounts = useAccounts(); const config = useConfig(); const taxes = useTaxCodes();
  const p = item?.profile;
  const accountOptions = (kind: 'revenue' | 'expense') => [{ value: '', label: 'Choose account' },
    ...postingAccounts(accounts.data, kind).map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))];
  return <FormDrawer title={item ? `Edit ${item.code}` : service ? 'New service' : 'New product'} eyebrow="Products & Services"
    width={640} onClose={onClose} initial={{ code: item?.code ?? '', name: item?.name ?? '', description: item?.description ?? '',
      kind: p?.kind ?? (service ? 'service' : 'nonstock'), unit_id: String(p?.unit_id ?? ''), category_id: String(p?.category_id ?? ''),
      currency: item?.currency ?? config.data?.base_currency ?? '', unit_price: item?.unit_price ?? '0',
      revenue_account_id: String(item?.revenue_account_id ?? ''), tax_code_id: String(item?.tax_code_id ?? ''),
      purchase_account_id: String(p?.purchase_account_id ?? ''), cogs_account_id: String(p?.cogs_account_id ?? ''),
      inventory_account_id: String(p?.inventory_account_id ?? ''), preferred_vendor_id: String(p?.preferred_vendor_id ?? ''),
      reorder_level: p?.reorder_level ?? '0', is_active: item?.is_active ?? true }}
    fields={[
      { key: 'code', label: 'SKU / service code', required: true }, { key: 'name', label: 'Name', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'kind', label: 'Classification', type: 'select', options: [{ value: 'nonstock', label: 'Non-stock product' }, { value: 'stock', label: 'Tracked product' }, { value: 'service', label: 'Service' }], hint: 'An established item retains its unit and classification.' },
      { key: 'unit_id', label: 'Unit of measure', type: 'select', required: true, options: [{ value: '', label: 'Choose unit' }, ...(units.data?.results ?? []).filter(u => u.is_active).map(u => ({ value: String(u.id), label: `${u.code} · ${u.name}` }))] },
      { key: 'category_id', label: 'Category', type: 'select', options: [{ value: '', label: 'Uncategorized' }, ...(categories.data?.results ?? []).filter(c => c.is_active).map(c => ({ value: String(c.id), label: c.name }))] },
      { key: 'currency', label: 'Default currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) },
      { key: 'unit_price', label: 'Fallback sales price', type: 'amount', hint: 'Dated price revisions take precedence in quotations.' },
      { key: 'revenue_account_id', label: 'Revenue account', type: 'select', options: accountOptions('revenue') },
      { key: 'purchase_account_id', label: 'Non-stock purchase account', type: 'select', options: accountOptions('expense') },
      { key: 'cogs_account_id', label: 'Cost of sales account', type: 'select', options: accountOptions('expense').filter(o => !o.value || accounts.data?.find(a => String(a.id) === o.value)?.account_type === 'expense') },
      { key: 'inventory_account_id', label: 'Inventory control account', type: 'select', options: [{ value: '', label: 'Not tracked / configure later' }, ...(accounts.data ?? []).filter(a => a.control === 'inventory' && a.is_active).map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))] },
      { key: 'tax_code_id', label: 'Default tax', type: 'select', options: [{ value: '', label: 'No tax' }, ...(taxes.data?.results ?? []).filter(t => t.is_active).map(t => ({ value: String(t.id), label: t.code }))] },
      { key: 'preferred_vendor_id', label: 'Preferred vendor', type: 'select', options: [{ value: '', label: 'None' }, ...(vendors.data?.results ?? []).map(v => ({ value: String(v.id), label: v.name }))] },
      { key: 'reorder_level', label: 'Reorder quantity (in selected unit)', type: 'amount' },
      { key: 'is_active', label: 'Active', type: 'checkbox' },
    ]} onSave={v => item ? api.patch(`/catalog/items/${item.id}/`, { ...body(v), revision: p?.revision }) : api.post('/catalog/items/', body(v))}>
    {!units.data?.count && <Banner tone="info">Create a unit of measure from the catalog toolbar before saving an item.</Banner>}
  </FormDrawer>;
}

function PriceDrawer({ item, onClose }: { item: CatalogItem; onClose: () => void }) {
  const config = useConfig();
  return <FormDrawer title="Add dated price" eyebrow={item.code} onClose={onClose} initial={{ purpose: 'sale', effective_date: today(), currency: item.currency, value: '', includes_tax: false, reason: '' }}
    fields={[{ key: 'purpose', label: 'Price purpose', type: 'select', options: [{ value: 'sale', label: 'Sales price' }, { value: 'purchase', label: 'Purchase price' }] },
      { key: 'effective_date', label: 'Effective from', type: 'date', required: true },
      { key: 'currency', label: 'Currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) },
      { key: 'value', label: 'Unit price', type: 'amount', required: true }, { key: 'includes_tax', label: 'Price includes tax', type: 'checkbox' },
      { key: 'reason', label: 'Revision reason', type: 'textarea', required: true }]}
    onSave={v => api.post(`/catalog/items/${item.id}/prices/`, body(v))}>
    <Banner tone="info">Price history is retained. Issued document snapshots never change when prices are revised.</Banner>
  </FormDrawer>;
}

export function CatalogDetail({ id }: { id: string }) {
  const query = useApi<CatalogItem>(`/catalog/items/${id}/`); const item = query.data;
  const [edit, setEdit] = useState(false); const [price, setPrice] = useState(false); const money = useMoney();
  const { can } = useAuth();
  const [scenario,setScenario]=useState(false);
  const [margin,setMargin]=useState<{date:string;currency:string;sale:string;cost:string;margin:string;percent:string|null}|null>(null);
  return <Screen eyebrow="Products & Services" title={item?.name ?? 'Catalog item'} description={item?.code}
    actions={item&&<><Button onClick={()=>setScenario(true)}>Margin scenario</Button>{can('catalog.manage')&&<><Button onClick={() => setEdit(true)}>Edit item</Button><Button variant="primary" onClick={() => setPrice(true)}>Add price revision</Button></>}</>}>
    {Boolean(query.error) && <Banner tone="err">{errorMessage(query.error)}</Banner>}
    {margin&&<InfoPanel title="Calculated scenario — not realized profit" rows={[{label:'Scenario date',value:formatDate(margin.date)},{label:'Sales amount',value:money(margin.sale,margin.currency)},{label:'Assumed cost',value:money(margin.cost,margin.currency)},{label:'Scenario margin',value:money(margin.margin,margin.currency)},{label:'Margin percentage',value:margin.percent===null?'No sales amount for comparison':`${margin.percent}%`}]} />}
    {scenario&&item&&<FormDrawer title="Margin scenario" eyebrow={item.code} initial={{date:today(),currency:item.currency,sale:'',cost:''}} onClose={()=>setScenario(false)}
      description="Compare an explicit sales amount with an assumed cost in the same currency. This does not change catalog prices, stock valuation, documents or posted profit."
      fields={[{key:'date',label:'Scenario date',type:'date',required:true},{key:'currency',label:'Scenario currency',hint:`Enter an enabled ISO currency code; default ${item.currency}.`,required:true},{key:'sale',label:'Sales amount',type:'amount',required:true},{key:'cost',label:'Assumed cost',type:'amount',required:true}]}
      saveLabel="Calculate scenario" success="Scenario calculated; no financial record changed" onSave={async v=>{const result=await api.post<NonNullable<typeof margin>>(`/catalog/items/${id}/margin/`,{...v,currency:String(v.currency).toUpperCase()});setMargin(result);return result;}} />}
    {item && <><InfoPanel title="Catalog identity" rows={[{ label: 'Code', value: item.code }, { label: 'Classification', value: item.profile?.kind ?? 'Legacy — not classified' },
      { label: 'Unit', value: item.unit }, { label: 'Fallback price', value: money(item.unit_price, item.currency) }, { label: 'Status', value: item.is_active ? 'Active' : 'Inactive' }]} />
      <ListPanel<PriceRevision> path={`/catalog/items/${id}/prices/`} title="Effective-dated prices" search={false} columns={[
        { key: 'date', label: 'Effective from', render: p => formatDate(p.effective_date) }, { key: 'purpose', label: 'Purpose', render: p => p.purpose },
        { key: 'price', label: 'Unit price', align: 'right', render: p => money(p.value, p.currency) }, { key: 'tax', label: 'Tax basis', render: p => p.includes_tax ? 'Inclusive' : 'Exclusive' },
        { key: 'reason', label: 'Revision reason', render: p => p.reason },
      ]} />{edit && <ItemDrawer item={item} service={item.profile?.kind === 'service'} onClose={() => setEdit(false)} />}{price && <PriceDrawer item={item} onClose={() => setPrice(false)} />}</>}
  </Screen>;
}

export function CatalogApp({ section, id }: { section: string; id?: string }) {
  const { can } = useAuth(); const money = useMoney(); const [create, setCreate] = useState(false);
  const [reference, setReference] = useState<'units' | 'categories' | null>(null);
  if (id) return <Gate allow={can('finance.view')}><CatalogDetail id={id} /></Gate>;
  const service = section === 'services';
  return <Gate allow={can('finance.view')}><Screen eyebrow="Products & Services" title={section === 'pricing' ? 'Pricing' : service ? 'Service Catalog' : 'Product Catalog'}
    description="One commercial identity across orders, purchasing and billing. Prices and quantities are validated by the server."
    actions={can('catalog.manage') && <><Button onClick={() => setReference('units')}>New unit</Button><Button onClick={() => setReference('categories')}>New category</Button><Button variant="primary" icon="add" onClick={() => setCreate(true)}>{service ? 'New service' : 'New product'}</Button></>}>
    {section === 'pricing' && <Banner tone="info">Select an item to review retained price history and add an effective-dated revision.</Banner>}
    <ListPanel<CatalogItem> path={`/catalog/items/${section === 'pricing' ? '' : `?kind=${service ? 'service' : 'product'}`}`} title="Catalog" columns={[
      { key: 'code', label: 'SKU / Code', render: i => <Primary mono href={`/catalog/${section}/${i.id}`} title={i.code} /> },
      { key: 'name', label: 'Item', render: i => <Primary title={i.name} sub={i.description} /> },
      { key: 'kind', label: 'Type', render: i => i.profile?.kind ?? 'Unclassified' }, { key: 'unit', label: 'Unit', render: i => i.unit },
      { key: 'price', label: 'Fallback price', align: 'right', render: i => money(i.unit_price, i.currency) },
      { key: 'status', label: 'Status', render: i => <StatusBadge status={i.is_active ? 'active' : 'paused'} /> },
    ]} />
    <Card title="Catalog setup"><div className="flex gap-5 p-4 text-[12px]"><Link href="/catalog/products">Products</Link><Link href="/catalog/services">Services</Link><Link href="/catalog/pricing">Dated pricing</Link></div></Card>
    {create && <ItemDrawer service={service} onClose={() => setCreate(false)} />}
    {reference && <ReferenceDrawer kind={reference} onClose={() => setReference(null)} />}
  </Screen></Gate>;
}
