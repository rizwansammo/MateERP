'use client';

import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { JournalLink, key } from '@/features/accounting/shared';
import { InfoPanel } from '@/components/ui/InfoPanel';
import { FormDrawer, Screen, type FieldSpec } from '@/features/commerce/forms';
import { ListPanel, Primary, useApi, today, useMoney } from '@/features/commerce/shared';
import type { SalesOrder } from '@/features/commerce/types';

interface Policy { id: number; order_line_id: number; trigger: string; contract_reference: string; reason: string; net_contract: string; controlled_quantity: string; snapshot: { quantity: string; item_code: string; currency: string } }
interface Location { id: number; code: string; name: string }
interface Dispatch { id: string; policy_id: number; date: string; quantity: string; reference: string; evidence: string; transit_location_id: number }
interface Control { id: string; policy_id: number; date: string; quantity: string; reference: string; evidence: string; currency: string; net_native: string; base_cogs: string; journal_id: string | null }
interface Return { id: number; date: string; quantity: string; reference: string; reason: string; base_cost: string }
interface Recall { id: number; date: string; quantity: string; reason: string }
type Action = { kind: 'policy' } | { kind: 'dispatch' | 'control'; policy: Policy } | { kind: 'return'; control: Control } | { kind: 'recall'; dispatch: Dispatch };

function FulfillmentDrawer({ order, action, onClose }: { order: SalesOrder; action: Action; onClose: () => void }) {
  const [operationKey] = useState(key);
  const locations = useApi<Page<Location>>('/inventory/locations/?page_size=100');
  const dispatches = useApi<Page<Dispatch>>(action.kind === 'control' ? `/billing/fulfillment/dispatches/?policy_id=${action.policy.id}&page_size=100` : null);
  const locationOptions = [{ value: '', label: 'Choose location' }, ...(locations.data?.results ?? []).map(l => ({ value: String(l.id), label: `${l.code} — ${l.name}` }))];
  const common: FieldSpec[] = [
    { key: 'date', label: 'Event date', type: 'date', required: true },
    { key: 'quantity', label: 'Quantity', type: 'amount', required: true },
    { key: 'reference', label: 'Source reference', required: true },
    { key: 'evidence', label: 'Evidence / acceptance reference', type: 'textarea', required: true },
  ];
  let fields: FieldSpec[] = common;
  let title = 'Record transfer of control';
  let description = 'Record the documented point at which the customer obtains control. This posts inventory/cost of sales and the contract revenue once. Invoice and payment are separate.';
  if (action.kind === 'policy') {
    title = 'Document recognition policy';
    description = 'For tracked products, document the actual contractual transfer-of-control condition. Dispatch or invoice timing alone does not establish that condition. The policy is retained as an immutable contract snapshot.';
    fields = [
      { key: 'order_line_id', label: 'Confirmed tracked product line', type: 'select', options: [{ value: '', label: 'Choose line' }, ...order.lines.map(l => ({ value: String(l.id), label: l.description }))] },
      { key: 'trigger', label: 'Recognition treatment', type: 'select', options: [{ value: 'control_transfer', label: 'Documented transfer of control' }, { value: 'invoice', label: 'Preserve already invoiced legacy treatment' }] },
      { key: 'contract_reference', label: 'Contract / authorization reference', required: true },
      { key: 'reason', label: 'Recognition condition and rationale', type: 'textarea', required: true },
    ];
  } else if (action.kind === 'dispatch') {
    title = 'Dispatch company-owned goods';
    description = 'Moves goods into a company-owned transit location. Dispatch creates no revenue, receivable or cost of sales.';
    fields = [...common, { key: 'from_location_id', label: 'From warehouse', type: 'select', options: locationOptions }, { key: 'transit_location_id', label: 'Company-owned transit location', type: 'select', options: locationOptions }];
  } else if (action.kind === 'control') {
    fields = [...common, { key: 'location_id', label: 'Stock location', type: 'select', options: locationOptions },
      { key: 'dispatch_id', label: 'Related dispatch', type: 'select', options: [{ value: '', label: 'Direct transfer from warehouse' }, ...(dispatches.data?.results ?? []).map(d => ({ value: d.id, label: `${d.reference} · ${d.quantity}` }))] }];
  } else {
    title = action.kind === 'return' ? 'Accept customer return' : 'Recall dispatched goods';
    description = action.kind === 'return' ? 'Restores inventory at the original fulfillment cost. Issue a credit note separately when authorized; accepting goods does not refund money or reverse revenue.' : 'Returns goods still owned by the company from transit. Goods already transferred to the customer require a customer return.';
    fields = [{ key: 'date', label: 'Event date', type: 'date' }, { key: 'quantity', label: 'Quantity', type: 'amount' },
      { key: 'location_id', label: 'Return warehouse', type: 'select', options: locationOptions },
      ...(action.kind === 'return' ? [{ key: 'reference', label: 'Return reference', required: true }] : []),
      { key: 'reason', label: 'Reason / inspection evidence', type: 'textarea', required: true }];
  }
  return <FormDrawer title={title} eyebrow="Sales fulfillment" description={description} fields={fields}
    initial={{ date: today(), quantity: '', reference: '', evidence: '', reason: '', trigger: 'control_transfer', order_line_id: '', contract_reference: '', location_id: '', from_location_id: '', transit_location_id: '', dispatch_id: '' }}
    onClose={onClose} saveLabel={action.kind === 'policy' ? 'Save contract policy' : 'Record event'} onSave={async v => {
      const root = '/billing/fulfillment/';
      if (action.kind === 'policy') return api.post(`${root}policies/`, { order_line_id: Number(v.order_line_id), trigger: v.trigger, contract_reference: v.contract_reference, reason: v.reason });
      const event = { date: v.date, quantity: v.quantity, key: operationKey };
      if (action.kind === 'return') return api.post(`${root}returns/`, { ...event, transfer_id: action.control.id, location_id: Number(v.location_id), reference: v.reference, reason: v.reason });
      if (action.kind === 'recall') return api.post(`${root}dispatches/${action.dispatch.id}/recall/`, { ...event, location_id: Number(v.location_id), reason: v.reason });
      const payload = { ...event, policy_id: action.policy.id, reference: v.reference, evidence: v.evidence };
      return action.kind === 'dispatch'
        ? api.post(`${root}dispatches/`, { ...payload, from_location_id: Number(v.from_location_id), transit_location_id: Number(v.transit_location_id) })
        : api.post(`${root}control-transfers/`, { ...payload, location_id: Number(v.location_id), ...(v.dispatch_id ? { dispatch_id: v.dispatch_id } : {}) });
    }} />;
}

export function OrderDetail({ id }: { id: string }) {
  const order = useApi<SalesOrder>(`/sales/orders/${id}/`);
  const { can } = useAuth(); const money = useMoney(); const [action, setAction] = useState<Action | null>(null);
  if (!order.data) return <Screen title="Sales order" eyebrow="Sales & Billing">{order.error ? <Banner tone="err">{errorMessage(order.error)}</Banner> : <Spinner />}</Screen>;
  const o = order.data;
  const manage = can('fulfillment.manage');
  return <Screen title={`${o.number} — ${o.customer_name}`} eyebrow="Sales & Billing" description="Dispatch, documented transfer of control, invoicing and collections retain separate source records."
    actions={manage && can('invoices.issue') && o.status !== 'draft' && o.status !== 'cancelled' && <Button variant="primary" onClick={() => setAction({ kind: 'policy' })}>Document recognition policy</Button>}>
    <InfoPanel title="Order" rows={[{ label: 'Status', value: o.status }, { label: 'Order date', value: formatDate(o.order_date) }, { label: 'Total including tax', value: money(o.total, o.currency) }, { label: 'Customer reference', value: o.customer_reference || '—' }]} />
    <ListPanel<Policy> path={`/billing/fulfillment/policies/?order_id=${id}`} title="Contract recognition policies" empty="No tracked-product policy documented. Existing service billing remains unchanged."
      columns={[
        { key: 'line', label: 'Product / contract', render: p => <Primary title={p.snapshot.item_code} sub={p.contract_reference} /> },
        { key: 'trigger', label: 'Recognition trigger', render: p => p.trigger === 'invoice' ? 'Existing invoice treatment' : 'Documented control transfer' },
        { key: 'quantity', label: 'Controlled / ordered', render: p => `${p.controlled_quantity} / ${p.snapshot.quantity}` },
        { key: 'net', label: 'Net contract', align: 'right', render: p => money(p.net_contract, p.snapshot.currency) },
        { key: 'actions', label: 'Actions', render: p => manage && <div className="flex gap-2">
          {can('inventory.manage') && <Button size="xs" onClick={() => setAction({ kind: 'dispatch', policy: p })}>Dispatch</Button>}
          {can('inventory.post') && can('invoices.issue') && <Button size="xs" variant="primary" onClick={() => setAction({ kind: 'control', policy: p })}>Transfer control</Button>}</div> },
      ]} />
    <ListPanel<Dispatch> path={`/billing/fulfillment/dispatches/?order_id=${id}`} title="Company-owned dispatches" columns={[
      { key: 'ref', label: 'Reference', render: d => <Primary mono title={d.reference} sub={d.evidence} /> }, { key: 'date', label: 'Date', render: d => formatDate(d.date) },
      { key: 'qty', label: 'Quantity', render: d => d.quantity }, { key: 'effect', label: 'Accounting effect', render: () => 'None — company-owned transit' },
      { key: 'act', label: 'Actions', render: d => manage && can('inventory.manage') && <Button size="xs" onClick={() => setAction({ kind: 'recall', dispatch: d })}>Recall</Button> },
    ]} />
    <ListPanel<Control> path={`/billing/fulfillment/control-transfers/?order_id=${id}`} title="Documented control transfers" columns={[
      { key: 'ref', label: 'Reference / evidence', render: d => <Primary mono title={d.reference} sub={d.evidence} /> }, { key: 'date', label: 'Date', render: d => formatDate(d.date) },
      { key: 'qty', label: 'Quantity', render: d => d.quantity }, { key: 'rev', label: 'Recognized revenue', align: 'right', render: d => money(d.net_native, d.currency) },
      { key: 'cost', label: 'Cost of sales', align: 'right', render: d => money(d.base_cogs) }, { key: 'journal', label: 'Journal', render: d => d.journal_id ? <JournalLink id={d.journal_id}>View journal</JournalLink> : 'No value posted' },
      { key: 'actions', label: 'Actions', render: d => manage && can('inventory.post') && <Button size="xs" onClick={() => setAction({ kind: 'return', control: d })}>Accept return</Button> },
    ]} />
    <ListPanel<Return> path={`/billing/fulfillment/returns/?order_id=${id}`} title="Customer returns" columns={[
      { key: 'ref', label: 'Reference', render: r => <Primary title={r.reference} sub={r.reason} /> }, { key: 'date', label: 'Date', render: r => formatDate(r.date) }, { key: 'qty', label: 'Quantity', render: r => r.quantity }, { key: 'value', label: 'Original cost restored', align: 'right', render: r => money(r.base_cost) },
    ]} />
    <ListPanel<Recall> path={`/billing/fulfillment/recalls/?order_id=${id}`} title="Dispatch recalls" columns={[
      { key: 'reason', label: 'Reason', render: r => r.reason }, { key: 'date', label: 'Date', render: r => formatDate(r.date) }, { key: 'qty', label: 'Quantity', render: r => r.quantity },
    ]} />
    {action && <FulfillmentDrawer order={o} action={action} onClose={() => setAction(null)} />}
  </Screen>;
}
