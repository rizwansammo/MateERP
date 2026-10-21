'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { InfoPanel } from '@/components/ui/InfoPanel';
import { StatGrid } from '@/components/ui/StatGrid';
import { BreakdownChart } from '@/features/commerce/Charts';
import { useAccounts } from '@/features/accounting/shared';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { Gate, ListPanel, Primary, StatusBadge, today, trimDecimal, useActionKey, useApi, useMoney } from '@/features/commerce/shared';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import type { CatalogItem, Reference, StockItem, StockMovement, Valuation } from './types';

interface InventorySummary {base_currency:string;as_of:string;stock_value:string;tracked_items:number;nonstock_items:number;unit_totals:{unit:string;quantity:string}[];low_stock_count:number;low_stock:{id:number;code:string;name:string;quantity:string;unit:string}[];locations:number;movements_this_month:number;by_item:{label:string;amount:string}[]}

function InventoryOverview() {
  const query=useApi<InventorySummary>('/inventory/summary/');const data=query.data;const money=useMoney();
  const units=data?.unit_totals??[];
  return <>{Boolean(query.error)&&<Banner tone="err">{errorMessage(query.error)}</Banner>}
    {!data&&!query.error&&<Banner tone="info">Loading inventory overview…</Banner>}
    {data&&<>
      {data.low_stock_count>0&&<Banner tone="warn">Reorder review: {data.low_stock.map((item,i)=><span key={item.id}>{i>0?' · ':''}<Link href={`/inventory/items/${item.id}`}>{item.name}</Link> ({trimDecimal(item.quantity)} {item.unit})</span>)}{data.low_stock_count>5&&<> · <Link href="/reports/low-stock">View all {data.low_stock_count} items</Link></>}</Banner>}
      <StatGrid minWidth={150} stats={[
        {label:'Stock value',value:money(data.stock_value,data.base_currency),sub:'Company weighted-average pool',accentBar:true},
        {label:'Tracked items',value:data.tracked_items,sub:`${data.nonstock_items} non-stock products`,accentBar:true},
        {label:units.length===1?'Units on hand':'Unit groups on hand',value:units.length===1?trimDecimal(units[0]!.quantity):units.length,sub:units.length===1?units[0]!.unit:'Quantities remain separate by unit',accentBar:true},
        {label:'Low / out of stock',value:data.low_stock_count,sub:'Current reorder thresholds',tone:data.low_stock_count?'err':'default'},
        {label:'Locations',value:data.locations,sub:'Active company-owned locations',accentBar:true},
        {label:'Movements this month',value:data.movements_this_month,sub:'Retained event legs',accentBar:true},
      ]} />
      <BreakdownChart title="Stock value by item" subtitle={`${data.base_currency} · current company cost pools · ${data.as_of}`} rows={data.by_item} currency={data.base_currency} compact emptyLabel="No stock value recorded." />
    </>}
  </>;
}

function LocationDrawer({ location, onClose }: { location?: Reference; onClose: () => void }) {
  return <FormDrawer title={location ? 'Edit warehouse location' : 'New warehouse location'} eyebrow="Inventory" width={480}
    initial={{ code: location?.code ?? '', name: location?.name ?? '', address: location?.address ?? '', is_active: location?.is_active ?? true }}
    fields={[{ key: 'code', label: 'Location code', required: true }, { key: 'name', label: 'Location name', required: true },
      { key: 'address', label: 'Address / notes', type: 'textarea' }, { key: 'is_active', label: 'Active', type: 'checkbox' }]}
    onClose={onClose} onSave={v => location ? api.patch(`/inventory/locations/${location.id}/`, body(v)) : api.post('/inventory/locations/', body(v))}>
    <Banner tone="info">A location holding stock cannot be deactivated. Transfers preserve the company-wide cost pool.</Banner>
  </FormDrawer>;
}

function StockActionDrawer({ transfer, valuation = false, onClose }: { transfer: boolean; valuation?: boolean; onClose: () => void }) {
  const items = useApi<Page<CatalogItem>>('/catalog/items/?kind=stock&status=active&page_size=100');
  const locations = useApi<Page<Reference>>('/inventory/locations/?page_size=100'); const accounts = useAccounts();
  const key = useActionKey(); const [selection, setSelection] = useState({ item: '', location: '' });
  const position = useApi<{ quantity: string }>(selection.item && selection.location ? `/inventory/position/?item_id=${selection.item}&location_id=${selection.location}` : null);
  const locationOptions = [{ value: '', label: 'Choose location' }, ...(locations.data?.results ?? []).filter(l => l.is_active).map(l => ({ value: String(l.id), label: `${l.code} · ${l.name}` }))];
  const originals=useApi<Page<StockMovement>>(selection.item?`/inventory/movements/?item_id=${selection.item}&page_size=100`:null);
  return <FormDrawer title={transfer ? 'Transfer stock' : valuation ? 'Correct retained stock valuation' : 'Record count adjustment'} eyebrow="Inventory" width={640} onClose={onClose}
    initial={{ item_id: '', location_id: '', from_location_id: '', to_location_id: '', date: today(), quantity: valuation?'0':'', base_value: '', offset_account_id: '', correction_of_id:'', reason: '' }}
    onValues={v => setSelection({ item: String(v.item_id), location: String(transfer ? v.from_location_id : v.location_id) })}
    fields={[{ key: 'item_id', label: 'Tracked item', type: 'select', required: true, options: [{ value: '', label: 'Choose item' }, ...(items.data?.results ?? []).map(i => ({ value: String(i.id), label: `${i.code} · ${i.name}` }))] },
      { key: transfer ? 'from_location_id' : 'location_id', label: transfer ? 'From location' : 'Counted location', type: 'select', options: locationOptions },
      ...(transfer ? [{ key: 'to_location_id', label: 'To location', type: 'select' as const, options: locationOptions }] : []),
      { key: 'date', label: 'Movement date', type: 'date', required: true },
      ...(!valuation?[{ key: 'quantity', label: transfer ? 'Quantity to move' : 'Quantity variance (+ increase / − decrease)', type: 'amount' as const, required: true }]:[]),
      ...(!transfer ? [{key:'correction_of_id',label:valuation?'Original stock event':'Corrects stock event (optional)',type:'select' as const,options:[{value:'',label:'Choose original event'},...(originals.data?.results??[]).map(m=>({value:m.id,label:`${formatDate(m.date)} · ${m.kind} · ${m.reason}`}))]},
        { key: 'base_value', label: valuation ? 'Signed cost correction (+ increase / − decrease)' : 'Documented base cost (increases only)', type: 'amount' as const },
        { key: 'offset_account_id', label: 'Adjustment expense account', type: 'select' as const, options: [{ value: '', label: 'Choose account' }, ...(accounts.data ?? []).filter(a => a.account_type === 'expense' && !a.control && a.is_active && a.is_postable).map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))] }] : []),
      { key: 'reason', label: 'Reason and evidence reference', type: 'textarea', required: true }]}
    success={result => !transfer && typeof result === 'object' && result !== null && 'status' in result && result.status === 'pending' ? 'Stock count submitted for independent approval; no adjustment posted' : 'Stock event recorded'}
    onSave={v => {
      if (!position.data) throw new Error('Load the selected location balance before submitting.');
      const {correction_of_id,...values}=v;
      return api.post(`/inventory/${transfer ? 'transfers' : 'adjustments'}/`, { ...body(values), ...(correction_of_id?{correction_of_id:String(correction_of_id)}:{}), ...(valuation?{kind:'valuation'}:{}), base_value: v.base_value || '0',
        expected_quantity: position.data.quantity, key: key.key });
    }}>
    {position.data && <Banner tone="info">Current book quantity: {position.data.quantity}. The server rechecks availability before recording this action.</Banner>}
    {Boolean(position.error) && <Banner tone="err">{errorMessage(position.error)}</Banner>}
    <Banner tone="info">Historical openings use the reviewed cutover workflow. Decreases use exact weighted-average cost; transfers never post cash or a second ledger.</Banner>
  </FormDrawer>;
}

function StockTable({overview=false}:{overview?:boolean}) {
  const money = useMoney();
  return <ListPanel<StockItem> path="/inventory/valuation/" title={overview?'Items & stock':'Company stock valuation'} columns={[
    { key: 'code', label: 'SKU', render: i => <Primary mono title={i.code} href={`/inventory/items/${i.id}`} /> },
    { key: 'name', label: 'Product', render: i => i.name }, { key: 'qty', label: 'Quantity', align: 'right', render: i => `${trimDecimal(i.quantity)} ${i.unit}` },
    { key: 'avg', label: 'Average cost', align: 'right', render: i => money(i.average_cost) }, { key: 'value', label: 'Value', align: 'right', render: i => money(i.value) },
    { key: 'reorder', label: 'Reorder at', align: 'right', render: i => `${trimDecimal(i.reorder_level)} ${i.unit}` },
  ]} />;
}

function StockHistory({ id, transfers = false }: { id?: string; transfers?: boolean }) {
  const money = useMoney();
  return <ListPanel<StockMovement> path={`/inventory/movements/${id ? `?item_id=${id}` : transfers ? '?kind=transfer_out' : ''}`} title={transfers ? 'Location transfers' : 'Immutable stock events'} columns={[
    { key: 'date', label: 'Date', render: m => formatDate(m.date) }, { key: 'item', label: 'Item', render: m => <Primary title={m.item_code} sub={m.item_name} /> },
    { key: 'kind', label: 'Movement', render: m => <StatusBadge status={m.kind} /> }, { key: 'location', label: 'Location', render: m => m.location_name },
    { key: 'qty', label: 'Quantity', align: 'right', render: m => trimDecimal(m.quantity) }, { key: 'value', label: 'Base value', align: 'right', render: m => money(m.base_value) },
    { key: 'source', label: 'Source / evidence', render: m => <Primary title={m.source_type} sub={m.reason} /> },
    { key: 'journal', label: 'Journal', render: m => m.journal_id ? <Link href={`/banking/journals/${m.journal_id}`}>View posting</Link> : 'No ledger change' },
  ]} />;
}

function StockDetail({ id }: { id: string }) {
  const item = useApi<CatalogItem>(`/catalog/items/${id}/`); const quantity = useApi<{ quantity: string; value: string; average_cost: string }>(`/inventory/position/?item_id=${id}`); const money = useMoney();
  return <Screen eyebrow="Inventory item" title={item.data?.name ?? 'Stock detail'} description={item.data?.code}>
    {Boolean(item.error || quantity.error) && <Banner tone="err">{errorMessage(item.error || quantity.error)}</Banner>}
    {quantity.data && <InfoPanel title="Company cost pool" rows={[{ label: 'Quantity', value: `${trimDecimal(quantity.data.quantity)} ${item.data?.unit ?? ''}` },
      { label: 'Inventory value', value: money(quantity.data.value) }, { label: 'Weighted-average unit cost', value: money(quantity.data.average_cost) }]} />}
    <StockHistory id={id} />
  </Screen>;
}

export function InventoryApp({ section, id }: { section: string; id?: string }) {
  const { can } = useAuth(); const [location, setLocation] = useState<Reference | 'new' | null>(null);
  const [action, setAction] = useState<'count' | 'transfer' | 'valuation' | null>(null); const money = useMoney();
  const valuation = useApi<Valuation>('/inventory/valuation/?page_size=1');
  const reconciliation=valuation.data&&<InfoPanel title="Inventory / GL reconciliation" rows={[{label:'Stock value',value:money(valuation.data.reconciliation.stock_value)},
    {label:'GL control',value:money(valuation.data.reconciliation.gl_value)},{label:'Difference',value:money(valuation.data.reconciliation.difference)}]} />;
  if (id) return <Gate allow={can('finance.view')}><StockDetail id={id} /></Gate>;
  const titles: Record<string, string> = { overview: 'Inventory Overview', items: 'Items & Stock', movements: 'Stock Movements', locations: 'Stock Locations', transfers: 'Transfers', valuation: 'Stock Valuation' };
  return <Gate allow={can('finance.view')}><Screen eyebrow="Inventory & Warehouse" title={titles[section] ?? 'Inventory'}
    description="Quantity events and historical weighted-average values reconcile to the general ledger. Units remain product-specific."
    actions={<>{can('inventory.manage') && section === 'locations' && <Button variant="primary" onClick={() => setLocation('new')}>New location</Button>}
      {can('inventory.manage') && section !== 'locations' && <Button onClick={() => setAction('transfer')}>Transfer stock</Button>}
      {can('inventory.post') && can('inventory.manage') && section !== 'locations' && <><Button variant="primary" onClick={() => setAction('count')}>Count adjustment</Button>
        {can('accounting.manage')&&<Button onClick={()=>setAction('valuation')}>Cost correction</Button>}</>}</>}>
    {Boolean(valuation.error) && <Banner tone="err">{errorMessage(valuation.error)}</Banner>}
    {section==='overview'&&<InventoryOverview />}
    {section!=='overview'&&reconciliation}
    {section === 'locations' ? <ListPanel<Reference> path="/inventory/locations/" columns={[
      { key: 'code', label: 'Code', render: l => <Primary mono title={l.code} /> }, { key: 'name', label: 'Location', render: l => l.name },
      { key: 'address', label: 'Address', render: l => l.address }, { key: 'active', label: 'Status', render: l => l.is_active ? 'Active' : 'Inactive' },
      { key: 'actions', label: 'Actions', render: l => can('inventory.manage') && <Button size="sm" onClick={() => setLocation(l)}>Edit</Button> },
    ]} /> : section === 'movements' || section === 'transfers' ? <StockHistory transfers={section === 'transfers'} /> : <StockTable overview={section==='overview'} />}
    {section==='overview'&&reconciliation}
    {section === 'overview' && <StockHistory />}
    {(section === 'overview' || section === 'movements') && <ListPanel<{ id: number; status: string; payload: { reason: string; quantity: string; date: string }; approval_id: number | null }>
      path="/inventory/counts/" title="Retained physical counts" columns={[
        { key: 'id', label: 'Count', render: c => `#${c.id}` }, { key: 'date', label: 'Date', render: c => formatDate(c.payload.date) },
        { key: 'reason', label: 'Evidence', render: c => c.payload.reason }, { key: 'qty', label: 'Variance', render: c => c.payload.quantity },
        { key: 'status', label: 'Status', render: c => <StatusBadge status={c.status} /> },
        { key: 'review', label: 'Review', render: c => c.approval_id ? <Link href="/settings/approvals">Approval history</Link> : 'Policy not required' },
      ]} />}
    {location && <LocationDrawer location={location === 'new' ? undefined : location} onClose={() => setLocation(null)} />}
    {action && <StockActionDrawer transfer={action === 'transfer'} valuation={action==='valuation'} onClose={() => setAction(null)} />}
  </Screen></Gate>;
}
