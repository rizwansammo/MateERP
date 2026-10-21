'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field } from '@/components/ui/Field';
import { Input, AmountInput, Select } from '@/components/ui/Input';
import { InfoPanel } from '@/components/ui/InfoPanel';
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table';
import { useAccounts, useConfig } from '@/features/accounting/shared';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { blankLine, DatedPriceButton, Totals, useCalculation, useItems, useTaxCodes, type EditLine } from '@/features/commerce/lines';
import { Card, ListPanel, Primary, StatusBadge, act, sumDecimals, today, useActionKey, useApi, useMoney } from '@/features/commerce/shared';
import type { Bill, Vendor } from '@/features/commerce/types';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import type { GoodsReceipt, PurchaseOrder, Reference } from './types';

function OrderDrawer({ order, amend = false, onClose }: { order?: PurchaseOrder; amend?: boolean; onClose: () => void }) {
  const config = useConfig(); const vendors = useApi<Page<Vendor>>('/purchasing/vendors/?status=active&page_size=100');
  const items = useItems(); const taxes = useTaxCodes();
  const [lines, setLines] = useState<EditLine[]>(order?.lines.map(l => ({ ...blankLine(),
    item_id: String(l.item_id), description: l.description, quantity: amend ? sumDecimals([l.quantity, `-${l.received_quantity}`]) : l.quantity, unit_price: l.unit_price,
    tax_code_id: String(l.tax_code_id ?? '') })) ?? [blankLine()]);
  const [currency, setCurrency] = useState(order?.currency ?? config.data?.base_currency ?? '');
  const [date, setDate] = useState(order?.date ?? today());
  const [inclusive, setInclusive] = useState(order?.prices_include_tax ?? false);
  const calculation = useCalculation({ lines, currency, date, pricesIncludeTax: inclusive });
  const setLine = (index: number, patch: Partial<EditLine>) => setLines(lines.map((l, i) => i === index ? { ...l, ...patch } : l));
  return <FormDrawer title={order ? `${amend ? 'Amend remainder of' : 'Edit'} ${order.number}` : 'New purchase order'} eyebrow="Procurement" width={900}
    onClose={onClose} extraDirty={Boolean(order ? JSON.stringify(lines) !== JSON.stringify(order.lines.map(l => ({ ...blankLine(), item_id: String(l.item_id), description: l.description, quantity: l.quantity, unit_price: l.unit_price, tax_code_id: String(l.tax_code_id ?? '') }))) : lines.some(l => l.item_id))}
    initial={{ vendor_id: String(order?.vendor_id ?? ''), date, currency, expected_date: order?.expected_date ?? '', prices_include_tax: inclusive, notes: order?.notes ?? '', reason: '' }}
    onValues={v => { setDate(String(v.date)); setCurrency(String(v.currency)); setInclusive(Boolean(v.prices_include_tax)); }}
    fields={[{ key: 'vendor_id', label: 'Vendor', type: 'select', required: true, options: [{ value: '', label: 'Choose vendor' }, ...(vendors.data?.results ?? []).map(v => ({ value: String(v.id), label: v.name }))] },
      { key: 'date', label: 'Order date', type: 'date', required: true }, { key: 'expected_date', label: 'Expected delivery', type: 'date' },
      { key: 'currency', label: 'Currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) },
      { key: 'prices_include_tax', label: 'Prices include tax', type: 'checkbox' }, { key: 'notes', label: 'Terms / notes', type: 'textarea' },
      ...(amend ? [{ key: 'reason', label: 'Amendment authority and reason', type: 'textarea' as const, required: true }] : [])]}
    onSave={v => {
      const data = { ...body(v), expected_date: v.expected_date || null, ...(order ? { revision: order.revision } : {}),
        lines: lines.map(l => ({ item_id: Number(l.item_id), description: l.description, quantity: l.quantity,
          unit_price: l.unit_price, tax_code_id: l.tax_code_id ? Number(l.tax_code_id) : null })) };
      return order ? amend ? api.post(`/purchasing/orders/${order.id}/amend/`, data) : api.patch(`/purchasing/orders/${order.id}/`, data) : api.post('/purchasing/orders/', data);
    }}>
    <div className="overflow-x-auto"><Table><THead><TR><TH>Catalog item</TH><TH>Description</TH><TH>Quantity</TH><TH>Unit price</TH><TH>Tax</TH><TH /></TR></THead><TBody>
      {lines.map((l, i) => <TR key={i}><TD><Select aria-label={`Line ${i + 1} item`} value={l.item_id} onChange={e => {
        const item = items.data?.results.find(x => String(x.id) === e.target.value);
        setLine(i, { item_id: e.target.value, description: item?.name ?? '', unit_price: item?.unit_price ?? '', tax_code_id: String(item?.tax_code_id ?? '') });
      }}><option value="">Choose item</option>{items.data?.results.map(item => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</Select>{l.item_id&&<DatedPriceButton itemId={l.item_id} date={date} currency={currency} quantity={l.quantity} includesTax={inclusive} purpose="purchase" onApply={price=>setLine(i,{unit_price:price})} />}</TD>
        <TD><Input aria-label={`Line ${i + 1} description`} value={l.description} onChange={e => setLine(i, { description: e.target.value })} /></TD>
        <TD><AmountInput aria-label={`Line ${i + 1} quantity`} value={l.quantity} onChange={e => setLine(i, { quantity: e.target.value })} /></TD>
        <TD><AmountInput aria-label={`Line ${i + 1} price`} value={l.unit_price} onChange={e => setLine(i, { unit_price: e.target.value })} /></TD>
        <TD><Select aria-label={`Line ${i + 1} tax`} value={l.tax_code_id} onChange={e => setLine(i, { tax_code_id: e.target.value })}><option value="">No tax</option>{taxes.data?.results.filter(t => t.is_active).map(t => <option key={t.id} value={t.id}>{t.code}</option>)}</Select></TD>
        <TD><Button size="sm" disabled={lines.length === 1} onClick={() => setLines(lines.filter((_, j) => j !== i))}>Remove</Button></TD></TR>)}
    </TBody></Table></div>
    <Button size="sm" onClick={() => setLines([...lines, blankLine()])}>Add line</Button>
    <Totals calc={calculation.result} error={calculation.error} currency={currency} />
    <Banner tone="info">Orders reserve no cash and post no payable. Approval freezes the exact revision; receiving and bills remain separate actions.</Banner>
    {amend && <Banner tone="warn">This creates a replacement draft and cancels the original unreceived remainder. Remove fully received lines. Submit the replacement for a new approval and issue it before receiving more goods.</Banner>}
  </FormDrawer>;
}

function ReceiveDrawer({ order, onClose }: { order: PurchaseOrder; onClose: () => void }) {
  const locations = useApi<Page<Reference>>('/inventory/locations/?page_size=100'); const action = useActionKey();
  return <FormDrawer title="Receive goods / accept service" eyebrow={order.number} width={620} onClose={onClose}
    initial={{ order_line_id: '', date: today(), quantity: '', rejected_quantity: '0', location_id: '', reference: '', reason: '' }}
    fields={[{ key: 'order_line_id', label: 'Order line', type: 'select', required: true, options: [{ value: '', label: 'Choose line' }, ...order.lines.map(l => ({ value: String(l.id), label: `${l.position}. ${l.description} · received ${l.received_quantity} / ${l.quantity}` }))] },
      { key: 'date', label: 'Acceptance date', type: 'date', required: true }, { key: 'quantity', label: 'Accepted quantity', type: 'amount', required: true },
      { key: 'rejected_quantity', label: 'Rejected quantity (never enters stock)', type: 'amount' },
      { key: 'location_id', label: 'Receiving location (tracked goods)', type: 'select', options: [{ value: '', label: 'Service — no warehouse' }, ...(locations.data?.results ?? []).filter(l => l.is_active).map(l => ({ value: String(l.id), label: l.name }))] },
      { key: 'reference', label: 'Delivery / acceptance reference', required: true }, { key: 'reason', label: 'Inspection / acceptance notes', type: 'textarea', required: true }]}
    onSave={v => api.post('/purchasing/receipts/', { ...body(v), key: action.key })}>
    <Banner tone="info">Accepted tracked goods post inventory against GRNI at the documented date rate. Service acceptance creates no stock. Over-delivery requires a separately authorized order.</Banner>
  </FormDrawer>;
}

export function PurchaseOrdersPage() {
  const { can } = useAuth(); const [create, setCreate] = useState(false); const money = useMoney();
  return <Screen eyebrow="Purchases & Expenses" title="Purchase Orders" description="Approved commitments, receiving and invoice matching. Order approval creates no ledger entry."
    actions={can('procurement.manage') && <Button variant="primary" icon="add" onClick={() => setCreate(true)}>New purchase order</Button>}>
    <ListPanel<PurchaseOrder> path="/purchasing/orders/" filters={[{ value: 'all', label: 'All' }, { value: 'draft', label: 'Draft', query: 'status=draft' },
      { value: 'pending', label: 'Pending', query: 'status=pending' }, { value: 'issued', label: 'Issued', query: 'status=issued' }, { value: 'partial', label: 'Partial', query: 'status=partial' },
      { value: 'received', label: 'Received', query: 'status=received' }, { value: 'closed', label: 'Closed', query: 'status=closed' }]} columns={[
      { key: 'number', label: 'Order', render: o => <Primary mono title={o.number} href={`/purchases/orders/${o.id}`} sub={`Revision ${o.revision}`} /> },
      { key: 'vendor', label: 'Vendor', render: o => o.vendor_name }, { key: 'date', label: 'Order date', render: o => formatDate(o.date) },
      { key: 'status', label: 'Status', render: o => <StatusBadge status={o.status} /> }, { key: 'total', label: 'Total', align: 'right', render: o => money(o.total, o.currency) },
    ]} />{create && <OrderDrawer onClose={() => setCreate(false)} />}
  </Screen>;
}

export function PurchaseOrderDetail({ id }: { id: string }) {
  const query = useApi<PurchaseOrder>(`/purchasing/orders/${id}/`); const order = query.data;
  const { can } = useAuth(); const money = useMoney(); const [edit, setEdit] = useState(false); const [receive, setReceive] = useState(false);
  const [amend, setAmend] = useState(false);
  const [correct, setCorrect] = useState<GoodsReceipt | null>(null);
  const [returnReceipt,setReturnReceipt]=useState<GoodsReceipt|null>(null);
  const [decision, setDecision] = useState<'submit' | 'issue' | 'cancel' | 'close' | null>(null);
  return <Screen eyebrow="Purchase order" title={order?.number ?? 'Loading…'} description={order?.vendor_name}
    actions={order && can('procurement.manage') && <>
      {['draft', 'rejected'].includes(order.status) && <Button onClick={() => setEdit(true)}>Edit draft</Button>}
      {order.status === 'draft' && <Button variant="primary" onClick={() => setDecision('submit')}>Submit for approval</Button>}
      {order.status === 'approved' && <Button variant="primary" onClick={() => setDecision('issue')}>Issue order</Button>}
      {['issued', 'partial'].includes(order.status) && <Button variant="primary" onClick={() => setReceive(true)}>Receive / accept</Button>}
      {['approved', 'issued', 'partial'].includes(order.status) && can('procurement.approve') && <Button onClick={() => setAmend(true)}>Amend remainder</Button>}
      {['partial', 'received'].includes(order.status) && can('procurement.approve') && <Button onClick={() => setDecision('close')}>Close order</Button>}
      {!['closed', 'cancelled', 'pending'].includes(order.status) && <Button variant="danger" onClick={() => setDecision('cancel')}>Cancel remainder</Button>}
    </>}>
    {Boolean(query.error) && <Banner tone="err">{errorMessage(query.error)}</Banner>}
    {order && <><InfoPanel title="Commitment" rows={[{ label: 'Status', value: <StatusBadge status={order.status} /> }, { label: 'Revision', value: order.revision },
      { label: 'Total', value: money(order.total, order.currency) }, { label: 'Tax', value: money(order.tax, order.currency) },
      { label: 'Approval', value: order.approval_id ? <Link href="/settings/approvals">Review approval</Link> : 'No pending request' }, { label: 'Expected', value: order.expected_date ? formatDate(order.expected_date) : 'Not specified' }]} />
      <Card title="Ordered vs received"><Table><THead><TR><TH>Item</TH><TH>Quantity</TH><TH>Received</TH><TH align="right">Net</TH><TH align="right">Total</TH></TR></THead><TBody>{order.lines.map(l => <TR key={l.id}><TD>{l.description}</TD><TD>{l.quantity}</TD><TD>{l.received_quantity}</TD><TD align="right">{money(l.taxable, order.currency)}</TD><TD align="right">{money(l.total, order.currency)}</TD></TR>)}</TBody></Table></Card>
      <ListPanel<GoodsReceipt> path={`/purchasing/receipts/?order=${id}`} title="Retained receiving evidence" columns={[
        { key: 'date', label: 'Accepted', render: r => formatDate(r.date) }, { key: 'item', label: 'Item', render: r => r.item_name },
        { key: 'quantity', label: 'Accepted / rejected', render: r => `${r.quantity} / ${r.rejected_quantity}` }, { key: 'ref', label: 'Reference', render: r => r.reference },
        { key: 'value', label: 'Historical base value', align: 'right', render: r => money(r.base_value) },
        { key: 'correction', label: 'Cost review', render: r => r.kind === 'goods' && can('procurement.approve') && can('inventory.post') && <Button size="xs" onClick={() => setCorrect(r)}>Review price variance</Button> },
        {key:'return',label:'Supplier return',render:r=>r.kind==='goods'&&can('procurement.manage')&&can('inventory.post')&&<Button size="xs" onClick={()=>setReturnReceipt(r)}>Return goods</Button>},
      ]} />{can('documents.vendor.view') && <ProcurementFiles order={order} />}
      {edit && <OrderDrawer order={order} onClose={() => setEdit(false)} />}{amend && <OrderDrawer order={order} amend onClose={() => setAmend(false)} />}{receive && <ReceiveDrawer order={order} onClose={() => setReceive(false)} />}</>}
    <ConfirmDialog open={decision !== null} title={`${decision ?? 'Review'} purchase order?`} confirmLabel={decision ?? 'Confirm'} reason={decision === 'cancel' || decision === 'close' ? 'required' : undefined}
      onCancel={() => setDecision(null)} onConfirm={async reason => { await act(() => api.post<PurchaseOrder>(`/purchasing/orders/${id}/${decision}/`, { reason }), r => r.status === 'pending' ? 'Submitted for independent approval' : `Order ${r.status}`); setDecision(null); }}>
      Approval freezes this revision. Accepted stock and posted liabilities are retained when the remaining commitment is closed or cancelled.
    </ConfirmDialog>
    {correct && <CostCorrectionDrawer receipt={correct} onClose={() => setCorrect(null)} />}
    {returnReceipt&&<SupplierReturnDrawer receipt={returnReceipt} onClose={()=>setReturnReceipt(null)} />}
  </Screen>;
}

function SupplierReturnDrawer({receipt,onClose}:{receipt:GoodsReceipt;onClose:()=>void}) {
  const action=useActionKey();const accounts=useAccounts();const money=useMoney();
  const locations=useApi<Page<Reference>>('/inventory/locations/?page_size=100');
  return <FormDrawer title="Supplier-accepted goods return" eyebrow={receipt.reference} width={780} onClose={onClose}
    description="Document an accepted cancellation of unmatched acquisition consideration. Original receipt FX is retained; stock leaves at company weighted-average cost and the difference is disclosed. No cash refund or AP settlement is invented."
    initial={{date:today(),quantity:'',location_id:'',variance_account_id:'',reference:'',reason:''}}
    fields={[{key:'date',label:'Return date',type:'date',required:true},{key:'quantity',label:'Accepted return quantity',type:'amount',required:true},
      {key:'location_id',label:'Return from location',type:'select',options:[{value:'',label:'Choose location'},...(locations.data?.results??[]).filter(l=>l.is_active).map(l=>({value:String(l.id),label:l.name}))]},
      {key:'variance_account_id',label:'Purchase-return cost variance account',type:'select',options:[{value:'',label:'Choose reviewed expense account'},...(accounts.data??[]).filter(a=>a.account_type==='expense'&&a.is_active&&a.is_postable&&!a.control).map(a=>({value:String(a.id),label:`${a.code} · ${a.name}`}))]},
      {key:'reference',label:'Supplier acceptance / cancellation reference',required:true},{key:'reason',label:'Supplier agreement and settlement treatment',type:'textarea',required:true}]}
    success={r=>typeof r==='object'&&r!==null&&'status' in r&&r.status==='pending'?'Supplier return submitted for independent approval; no financial effect posted':'Supplier return posted and original source retained'}
    onSave={v=>api.post(`/purchasing/receipts/${receipt.id}/supplier-returns/`,{...body(v),key:action.key})}>
    <Banner tone="info">Draft receipt matches must be removed first. A posted bill needs its owning correction workflow; settled or reconciled liabilities cannot be reduced by a stock return. Pending requests are reviewed in <Link href="/settings/approvals">Approvals</Link>.</Banner>
    <ListPanel<{id:number;date:string;quantity:string;reference:string;base_value:string;inventory_value:string;variance:string;journal_id:string}>
      path={`/purchasing/receipts/${receipt.id}/supplier-returns/`} title="Retained supplier returns" columns={[
        {key:'date',label:'Date',render:r=>formatDate(r.date)},{key:'ref',label:'Acceptance',render:r=>r.reference},{key:'qty',label:'Quantity',render:r=>r.quantity},
        {key:'base',label:'GRNI cancellation',render:r=>money(r.base_value)},{key:'inventory',label:'Stock removed',render:r=>money(r.inventory_value)},
        {key:'variance',label:'Cost variance',render:r=>money(r.variance)},{key:'journal',label:'Source',render:r=><Link href={`/banking/journals/${r.journal_id}`}>Posting</Link>},
      ]} />
  </FormDrawer>;
}

function CostCorrectionDrawer({ receipt, onClose }: { receipt: GoodsReceipt; onClose: () => void }) {
  const accounts = useAccounts(); const action = useActionKey(); const money = useMoney();
  return <FormDrawer title="Review supplier price variance" eyebrow={receipt.reference} width={680} onClose={onClose}
    description="Correct a wholly unmatched goods receipt. Original receipts, bills and journals remain unchanged. The authorized difference is split between retained inventory and a disclosed consumed-cost correction. Historical receipt FX is retained; bill-date FX is handled separately."
    initial={{ date: today(), new_net_cost: '', variance_account_id: '', reason: '' }}
    fields={[{ key: 'date', label: 'Permitted recognition date', type: 'date', required: true }, { key: 'new_net_cost', label: 'Correct total net acquisition cost (receipt currency)', type: 'amount', required: true },
      { key: 'variance_account_id', label: 'Consumed cost / cost-of-sales expense account', type: 'select', options: [{ value: '', label: 'Choose reviewed cost account' }, ...(accounts.data ?? []).filter(a => a.account_type === 'expense' && a.is_active && a.is_postable && !a.control).map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))] },
      { key: 'reason', label: 'Supplier evidence and correction rationale', type: 'textarea', required: true }]}
    success={r => r !== null && typeof r === 'object' && 'status' in r && r.status === 'pending' ? 'Price correction submitted for independent approval' : 'Acquisition cost correction posted'}
    onSave={v => api.post(`/purchasing/receipts/${receipt.id}/cost-correction/`, { ...body(v), key: action.key })}>
    <ListPanel<{ id: number; date: string; inventory_delta: string; consumed_delta: string; reason: string }>
      path={`/purchasing/receipts/${receipt.id}/cost-corrections/`} title="Retained price corrections" columns={[
        { key: 'date', label: 'Date', render: c => formatDate(c.date) }, { key: 'inv', label: 'Inventory', align: 'right', render: c => money(c.inventory_delta) },
        { key: 'consumed', label: 'Consumed cost', align: 'right', render: c => money(c.consumed_delta) }, { key: 'reason', label: 'Evidence', render: c => c.reason },
      ]} />
  </FormDrawer>;
}

function ProcurementFiles({ order }: { order: PurchaseOrder }) {
  const { can } = useAuth(); const [open, setOpen] = useState(false); const [file, setFile] = useState<File | null>(null);
  const receipts = useApi<Page<GoodsReceipt>>(open ? `/purchasing/receipts/?order=${order.id}&page_size=100` : null);
  return <>
    <ListPanel<{ id: number; file_id: string; name: string; description: string; receipt_id: number | null }>
      path={`/purchasing/orders/${order.id}/evidence/`} title="Private purchase / receiving evidence" search={false}
      actions={can('documents.manage') && can('procurement.manage') && <Button size="sm" onClick={() => setOpen(true)}>Upload evidence</Button>}
      columns={[{ key: 'name', label: 'File', render: f => <a href={`/api/v1/files/${f.file_id}/content/`} target="_blank" rel="noreferrer">{f.name}</a> },
        { key: 'description', label: 'Evidence', render: f => f.description }, { key: 'receipt', label: 'Receipt', render: f => f.receipt_id ? `#${f.receipt_id}` : 'Purchase order' }]} />
    {open && <FormDrawer title="Upload purchase evidence" eyebrow={order.number} onClose={() => setOpen(false)} initial={{ description: '', receipt_id: '' }}
      fields={[{ key: 'description', label: 'Description / purpose', required: true }, { key: 'receipt_id', label: 'Related receipt (optional)', type: 'select', options: [{ value: '', label: 'Purchase order evidence' }, ...(receipts.data?.results ?? []).map(r => ({ value: String(r.id), label: `${r.reference} · ${r.item_name}` }))] }]}
      onSave={v => { if (!file) throw new Error('Select a PDF or image.'); const form = new FormData(); form.set('file', file); form.set('description', String(v.description)); if (v.receipt_id) form.set('receipt_id', String(v.receipt_id)); return api.post(`/purchasing/orders/${order.id}/evidence/`, form); }}>
      <Field htmlFor="procurement-file" label="Document (PDF, PNG, JPEG or WEBP)"><Input id="procurement-file" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)} /></Field>
      <Banner tone="info">Evidence remains private and retained. Validation checks file content; malware scanning is not claimed.</Banner>
    </FormDrawer>}
  </>;
}

export function ReceiptMatching({ bill }: { bill: Bill }) {
  const [open, setOpen] = useState(false); const receipts = useApi<Page<GoodsReceipt>>(open ? `/purchasing/receipts/?vendor=${bill.vendor_id}&page_size=100` : null);
  const { can } = useAuth();
  if (bill.status !== 'draft' || !can('procurement.manage') || !can('bills.manage')) return null;
  return <><Button onClick={() => setOpen(true)}>Match accepted receipts</Button>{open && <FormDrawer title="Match bill line to a receipt" eyebrow={bill.vendor_reference} onClose={() => setOpen(false)}
    initial={{ bill_line_id: '', receipt_id: '', quantity: '' }} fields={[
      { key: 'bill_line_id', label: 'Bill line', type: 'select', options: [{ value: '', label: 'Choose bill line' }, ...bill.lines.map(l => ({ value: String(l.id), label: l.description }))] },
      { key: 'receipt_id', label: 'Accepted receipt', type: 'select', options: [{ value: '', label: 'Choose receipt' }, ...(receipts.data?.results ?? []).map(r => ({ value: String(r.id), label: `${r.order_number} · ${r.item_name} · ${r.reference}` }))] },
      { key: 'quantity', label: 'Matched quantity', type: 'amount', required: true },
    ]} onSave={v => api.post('/purchasing/receipts/match/', { bill_line_id: Number(v.bill_line_id), receipts: [{ receipt_id: Number(v.receipt_id), quantity: v.quantity }] })}>
    <Banner tone="info">Exact receipt quantity and net cost must match the full bill line. Split bill lines for partial deliveries. Posting clears historical GRNI; it does not purchase the stock again.</Banner>
  </FormDrawer>}</>;
}
