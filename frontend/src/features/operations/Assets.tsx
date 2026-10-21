'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { InfoPanel } from '@/components/ui/InfoPanel';
import { Input } from '@/components/ui/Input';
import { Table, THead, TBody, TH, TD, TR } from '@/components/ui/Table';
import { Spinner } from '@/components/ui/Spinner';
import { JournalLink, useAccounts } from '@/features/accounting/shared';
import { FormDrawer, Screen, body, type FieldSpec } from '@/features/commerce/forms';
import { Card, Gate, ListPanel, Primary, StatusBadge, today, useActionKey, useApi, useMoney } from '@/features/commerce/shared';
import type { Invoice, InvoiceRow } from '@/features/commerce/types';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';

interface Asset { id: string; tag: string; name: string; category: string; description: string; serial_number: string; location: string; custodian_reference: string; acquisition_date: string; recognition_date: string; in_service_date: string; cost: string; accumulated: string; book_value: string; status: string; cancellation?:{date:string;reason:string;journal_id:string}|null; source_line_id: number; journal_id: string; source_snapshot: { currency: string; exchange_rate: string; journal_number: string; journal_id: string; original_debit: string } }
interface ScheduleRow { month: string; scheduled: string; posted: string; recognition_date: string | null; journal_id: string | null; version: number }
interface Acquisition { id: number; journal_number: string; date: string; account_code: string; description: string; source_reference: string; currency: string; available_base: string }
interface AssetActionResult { status: string; result_id: string; approval_id: number | null }
interface AssetReconciliation { cost: string; cost_ledger: string; cost_difference: string; depreciation: string; depreciation_ledger: string; depreciation_difference: string }
interface Disposal { id: number; asset_id: string; date: string; kind: string; proceeds_base: string; book_value: string; gain_loss: string; journal_id: string; reason: string }
interface Charge { id: number; asset_id: string; month: string; recognition_date: string; amount: string; journal_id: string }

function resultMessage(result: unknown) {
  return typeof result === 'object' && result !== null && 'status' in result && result.status === 'pending' ? 'Asset action submitted for independent approval; no financial effect posted' : 'Asset action recorded';
}

function RegisterDrawer({ onClose }: { onClose: () => void }) {
  const sources = useApi<Page<Acquisition>>('/assets/acquisitions/?page_size=100');
  const accounts = useAccounts(); const action = useActionKey(); const money = useMoney();
  return <FormDrawer title="Capitalize fixed asset" eyebrow="Fixed Assets" width={760} onClose={onClose}
    description="Claim a real posted acquisition debit once. Capitalization reclassifies its cost; it does not create another purchase, payable or bank payment. Correcting an expense classification also requires accounting authority."
    initial={{ tag: '', name: '', category: '', description: '', serial_number: '', location: '', custodian_reference: '', source_line_id: '', cost: '', residual: '0', useful_life_months: '60', recognition_date: today(), in_service_date: today(), depreciation_account_id: '', reason: '' }}
    fields={[
      { key: 'tag', label: 'Unique asset tag', required: true }, { key: 'name', label: 'Asset name', required: true },
      { key: 'category', label: 'Category', required: true }, { key: 'serial_number', label: 'Serial number' }, { key: 'location', label: 'Location' },
      { key: 'custodian_reference', label: 'Custodian / external contact reference', hint: 'A contact reference; no HR account is created.' },
      { key: 'source_line_id', label: 'Posted acquisition source', type: 'select', w: 'full', options: [{ value: '', label: 'Choose posted source debit' }, ...(sources.data?.results ?? []).map(s => ({ value: String(s.id), label: `${s.journal_number} · ${s.source_reference} · ${s.account_code} · ${money(s.available_base)} available` }))] },
      { key: 'cost', label: 'Historical cost claimed (company base currency)', type: 'amount', required: true }, { key: 'recognition_date', label: 'Capitalization recognition date', type: 'date', required: true },
      { key: 'in_service_date', label: 'Available for use', type: 'date', required: true }, { key: 'useful_life_months', label: 'Useful life (months)', type: 'number', required: true },
      { key: 'residual', label: 'Residual value (base currency)', type: 'amount', required: true },
      { key: 'depreciation_account_id', label: 'Depreciation expense account', type: 'select', options: [{ value: '', label: 'Choose expense account' }, ...(accounts.data ?? []).filter(a => a.account_type === 'expense' && a.is_active && a.is_postable && !a.control).map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))] },
      { key: 'description', label: 'Description', type: 'textarea' }, { key: 'reason', label: 'Capitalization authority / reclassification evidence', type: 'textarea', required: true },
    ]} success={resultMessage} onSave={v => api.post<AssetActionResult>('/assets/register/', { ...body(v), useful_life_months: Number(v.useful_life_months), key: action.key })}>
    {Boolean(sources.error) && <Banner tone="err">{errorMessage(sources.error)}</Banner>}
    <Banner tone="info">Recoverable tax and inventory control debits cannot be claimed. Historical purchase currency and FX remain on the source snapshot.</Banner>
  </FormDrawer>;
}

function ActionDrawer({ asset, kind, row, onClose }: { asset: Asset; kind: 'depreciation' | 'estimate' | 'disposal' | 'cancel'; row?: ScheduleRow; onClose: () => void }) {
  const action = useActionKey(); const accounts = useAccounts(); const money = useMoney();
  const [invoiceId, setInvoiceId] = useState('');
  const invoices = useApi<Page<InvoiceRow>>(kind === 'disposal' ? '/billing/invoices/?status=issued&page_size=100' : null);
  const invoice = useApi<Invoice>(invoiceId ? `/billing/invoices/${invoiceId}/` : null);
  const expenseOptions = [{ value: '', label: 'Choose loss expense account' }, ...(accounts.data ?? []).filter(a => a.account_type === 'expense' && a.is_active && a.is_postable && !a.control).map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))];
  let fields: FieldSpec[];
  let title: string;
  let description: string;
  if (kind === 'cancel') {
    title='Reverse unused capitalization';description='Reverse the original capitalization in a permitted period and release its source claim. Original records remain retained. Posted depreciation or disposal prevents this simple correction.';
    fields=[{key:'recognition_date',label:'Permitted reversal date',type:'date',required:true},{key:'reason',label:'Correction authority and rationale',type:'textarea',required:true}];
  } else if (kind === 'depreciation') {
    title = `Post depreciation — ${row?.month.slice(0,7)}`;
    description = `Scheduled charge: ${money(row?.scheduled)}. Approval and posting are separate from the planned schedule. A later permitted recognition date preserves the original service month and requires accounting authority.`;
    fields = [{ key: 'recognition_date', label: 'Permitted accounting date', type: 'date', required: true }, { key: 'reason', label: 'Posting basis / delayed recognition reason', type: 'textarea', required: true }];
  } else if (kind === 'estimate') {
    title = 'Revise depreciation estimate'; description = 'A new prospective version starts at the first unposted month. Previously posted charges and estimates remain unchanged.';
    fields = [{ key: 'effective_date', label: 'First unposted month (first day)', type: 'date' }, { key: 'remaining_months', label: 'Remaining useful life (months)', type: 'number' }, { key: 'residual', label: 'Revised residual (base currency)', type: 'amount' }, { key: 'reason', label: 'Estimate authority and rationale', type: 'textarea', required: true }];
  } else {
    title = 'Record asset disposal'; description = 'Post earlier service months first. The disposal month is prorated through the selected date. A sale uses an issued, uncredited asset-sale invoice on that same effective date; its gross revenue is reclassified to the exact gain/loss. This action never records a bank collection.';
    fields = [{ key: 'date', label: 'Disposal date', type: 'date' }, { key: 'kind', label: 'Disposal type', type: 'select', options: [{ value: 'retirement', label: 'Retirement — no proceeds' }, { value: 'write_off', label: 'Write-off — no proceeds' }, { value: 'sale', label: 'Sale — issued receivable' }] },
      { key: 'invoice_id', label: 'Issued asset-sale invoice (sales only)', type: 'select', options: [{ value: '', label: 'No invoice for retirement / write-off' }, ...(invoices.data?.results ?? []).map(i => ({ value: String(i.id), label: `${i.number} · ${i.customer_name}` }))] },
      { key: 'invoice_line_id', label: 'Asset-sale invoice line', type: 'select', options: [{ value: '', label: 'Choose the dedicated asset-sale line' }, ...(invoice.data?.lines ?? []).map(l => ({ value: String(l.id), label: l.description }))] },
      { key: 'gain_account_id', label: 'Disposal gain account', type: 'select', options: [{ value: '', label: 'Choose gain revenue account' }, ...(accounts.data ?? []).filter(a => a.account_type === 'revenue' && a.is_active && a.is_postable && !a.control).map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))] },
      { key: 'loss_account_id', label: 'Disposal loss account', type: 'select', options: expenseOptions }, { key: 'reason', label: 'Disposal evidence and authorization', type: 'textarea', required: true }];
  }
  const monthEnd = row ? new Date(Number(row.month.slice(0,4)), Number(row.month.slice(5,7)), 0).toLocaleDateString('en-CA') : today();
  return <FormDrawer title={title} eyebrow={asset.tag} description={description} width={720} onClose={onClose}
    initial={{ recognition_date: monthEnd, effective_date: row?.month ?? '', remaining_months: '', residual: '0', date: today(), kind: 'retirement', invoice_id: '', invoice_line_id: '', gain_account_id: '', loss_account_id: '', reason: '' }}
    onValues={v => setInvoiceId(String(v.invoice_id))} fields={fields} success={resultMessage} onSave={v => {
      if(kind==='cancel')return api.post(`/assets/register/${asset.id}/cancel_capitalization/`,{recognition_date:v.recognition_date,reason:v.reason,key:action.key});
      if (kind === 'depreciation') return api.post(`/assets/register/${asset.id}/depreciate/`, { month: row?.month, recognition_date: v.recognition_date, reason: v.reason, key: action.key });
      if (kind === 'estimate') return api.post(`/assets/register/${asset.id}/revise_estimate/`, { effective_date: v.effective_date, remaining_months: Number(v.remaining_months), residual: v.residual, reason: v.reason, key: action.key });
      return api.post(`/assets/register/${asset.id}/dispose/`, { date: v.date, kind: v.kind, ...(v.invoice_line_id ? { invoice_line_id: Number(v.invoice_line_id) } : {}), ...(v.gain_account_id ? { gain_account_id: Number(v.gain_account_id) } : {}), ...(v.loss_account_id ? { loss_account_id: Number(v.loss_account_id) } : {}), reason: v.reason, key: action.key });
    }} />;
}

function AssetFiles({ asset }: { asset: Asset }) {
  const { can } = useAuth(); const [upload, setUpload] = useState(false); const [file, setFile] = useState<File | null>(null);
  return <><ListPanel<{ id: number; file_id: string; name: string; description: string }> path={`/assets/register/${asset.id}/evidence/`} title="Private supporting evidence"
    actions={can('assets.manage') && can('documents.manage') && <Button size="sm" onClick={() => setUpload(true)}>Upload evidence</Button>} columns={[
      { key: 'name', label: 'Document', render: f => <Link href={`/api/v1/files/${f.file_id}/content/`} target="_blank">{f.name}</Link> }, { key: 'description', label: 'Purpose', render: f => f.description },
    ]} />{upload && <FormDrawer title="Upload asset evidence" eyebrow={asset.tag} onClose={() => setUpload(false)} fields={[{ key: 'description', label: 'Description / purpose', required: true }]} initial={{ description: '' }}
      onSave={v => { if (!file) throw new Error('Choose a PDF or approved image.'); const data = new FormData(); data.set('file', file); data.set('description', String(v.description)); return api.post(`/assets/register/${asset.id}/evidence/`, data); }}>
      <Field label="Document (PDF, PNG, JPEG or WEBP)" htmlFor="asset-file"><Input id="asset-file" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)} /></Field>
    </FormDrawer>}</>;
}

function AssetDetail({ id }: { id: string }) {
  const query = useApi<Asset>(`/assets/register/${id}/`); const planned = useApi<ScheduleRow[]>(`/assets/register/${id}/schedule/`);
  const { can } = useAuth(); const money = useMoney(); const [action, setAction] = useState<'depreciation' | 'estimate' | 'disposal' | 'cancel' | null>(null); const [edit, setEdit] = useState(false);
  const asset = query.data; const next = planned.data?.find(r => r.journal_id === null && !/^0(?:\.0+)?$/.test(r.scheduled));
  if (!asset) return <Screen title="Fixed asset" eyebrow="Fixed Assets">{query.error ? <Banner tone="err">{errorMessage(query.error)}</Banner> : <Spinner />}</Screen>;
  const manage = can('assets.manage') && can('assets.post') && asset.status === 'active';
  return <Screen title={`${asset.tag} — ${asset.name}`} eyebrow="Fixed Assets" description="Historical acquisition, planned charges and posted depreciation remain independently traceable."
    actions={<>{can('assets.manage') && <Button onClick={() => setEdit(true)}>Edit asset details</Button>}{manage && <><Button onClick={() => setAction('estimate')}>Revise estimate</Button><Button onClick={() => setAction('disposal')}>Record disposal</Button>{next && <Button variant="primary" onClick={() => setAction('depreciation')}>Post next depreciation</Button>}{can('accounting.manage')&&<Button variant="danger" onClick={()=>setAction('cancel')}>Reverse capitalization</Button>}</>}</>}>
    <InfoPanel title="Asset register" rows={[{ label: 'Status', value: asset.status }, { label: 'Historical cost', value: money(asset.cost) }, { label: 'Accumulated posted depreciation', value: money(asset.accumulated) }, { label: 'Net book value', value: money(asset.book_value) }, { label: 'Acquisition date', value: formatDate(asset.acquisition_date) }, { label: 'Capitalization date', value: formatDate(asset.recognition_date) }, { label: 'Available for use', value: formatDate(asset.in_service_date) }, { label: 'Location', value: asset.location || '—' }, { label: 'Custodian reference', value: asset.custodian_reference || '—' }, { label: 'Original source', value: <JournalLink id={asset.source_snapshot.journal_id}>{asset.source_snapshot.journal_number}</JournalLink> }, { label: 'Purchase currency / historical FX', value: `${asset.source_snapshot.currency} · ${asset.source_snapshot.exchange_rate}` }]} />
    {Boolean(planned.error) && <Banner tone="err">{errorMessage(planned.error)}</Banner>}
    <Card title="Straight-line depreciation — planned vs posted"><div className="max-h-[500px] overflow-auto"><Table><THead><TR><TH>Service month</TH><TH>Estimate</TH><TH align="right">Scheduled</TH><TH align="right">Posted</TH><TH>Recognition date</TH><TH>Journal</TH></TR></THead><TBody>{planned.data?.map(r => <TR key={r.month}><TD>{r.month.slice(0,7)}</TD><TD>v{r.version}</TD><TD align="right">{money(r.scheduled)}</TD><TD align="right">{money(r.posted)}</TD><TD>{r.recognition_date ? formatDate(r.recognition_date) : 'Planned only'}</TD><TD>{r.journal_id ? <JournalLink id={r.journal_id}>View journal</JournalLink> : 'Not posted'}</TD></TR>)}</TBody></Table></div></Card>
    <ListPanel<{ id: number; version: number; effective_date: string; remaining_months: number; residual: string; reason: string }> path={`/assets/register/${id}/estimates/`} title="Retained estimate revisions" columns={[
      { key: 'version', label: 'Version', render: r => `v${r.version}` }, { key: 'date', label: 'Effective', render: r => formatDate(r.effective_date) }, { key: 'life', label: 'Months', render: r => r.remaining_months }, { key: 'residual', label: 'Residual', align: 'right', render: r => money(r.residual) }, { key: 'reason', label: 'Evidence', render: r => r.reason },
    ]} />
    {asset.cancellation&&<Banner tone="info">Capitalization reversed on {formatDate(asset.cancellation.date)} · {asset.cancellation.reason} · <JournalLink id={asset.cancellation.journal_id}>Reversal journal</JournalLink></Banner>}
    <AssetFiles asset={asset} />
    {edit && <FormDrawer title="Edit asset details" eyebrow={asset.tag} onClose={() => setEdit(false)} initial={{ name: asset.name, category: asset.category, description: asset.description, serial_number: asset.serial_number, location: asset.location, custodian_reference: asset.custodian_reference }} fields={[
      { key: 'name', label: 'Asset name' }, { key: 'category', label: 'Category' }, { key: 'serial_number', label: 'Serial number' }, { key: 'location', label: 'Location' }, { key: 'custodian_reference', label: 'Custodian reference' }, { key: 'description', label: 'Description', type: 'textarea' },
    ]} onSave={v => api.patch(`/assets/register/${id}/`, v)} />}
    {action && <ActionDrawer asset={asset} kind={action} row={next} onClose={() => setAction(null)} />}
  </Screen>;
}

export function AssetsApp({ section, id }: { section: string; id?: string }) {
  const { can } = useAuth(); const money = useMoney(); const [create, setCreate] = useState(false);
  const rec = useApi<AssetReconciliation>(can('finance.view') ? '/assets/register/reconciliation/' : null);
  return <Gate allow={can('finance.view')}>{id ? <AssetDetail id={id} /> : <Screen title={section === 'depreciation' ? 'Depreciation' : section === 'disposal' ? 'Asset Disposal' : 'Asset Register'} eyebrow="Fixed Assets"
    description="Source-linked acquisitions, immutable depreciation and documented disposals. Planned charges create no accounting entries."
    actions={can('assets.manage') && can('assets.post') && <Button variant="primary" icon="add" onClick={() => setCreate(true)}>Capitalize asset</Button>}>
    {Boolean(rec.error) && <Banner tone="err">{errorMessage(rec.error)}</Banner>}
    {rec.data && <InfoPanel title="Asset register / GL reconciliation" rows={[{ label: 'Active historical cost', value: money(rec.data.cost) }, { label: 'Cost difference to GL', value: money(rec.data.cost_difference) }, { label: 'Active accumulated depreciation', value: money(rec.data.depreciation) }, { label: 'Depreciation difference to GL', value: money(rec.data.depreciation_difference) }]} />}
    {section === 'depreciation' ? <ListPanel<Charge> path="/assets/depreciation/" title="Posted charges" columns={[
      { key: 'asset', label: 'Asset', render: c => <Link href={`/assets/register/${c.asset_id}`}>Asset details</Link> }, { key: 'month', label: 'Service month', render: c => c.month.slice(0,7) }, { key: 'date', label: 'Recognition date', render: c => formatDate(c.recognition_date) }, { key: 'amount', label: 'Actual posted', align: 'right', render: c => money(c.amount) }, { key: 'journal', label: 'Journal', render: c => <JournalLink id={c.journal_id}>View journal</JournalLink> },
    ]} /> : section === 'disposal' ? <ListPanel<Disposal> path="/assets/disposals/" columns={[
      { key: 'asset', label: 'Asset', render: d => <Link href={`/assets/register/${d.asset_id}`}>Asset details</Link> }, { key: 'date', label: 'Date', render: d => formatDate(d.date) }, { key: 'kind', label: 'Treatment', render: d => d.kind }, { key: 'proceeds', label: 'Proceeds / receivable', align: 'right', render: d => money(d.proceeds_base) }, { key: 'book', label: 'Book value removed', align: 'right', render: d => money(d.book_value) }, { key: 'gain', label: 'Gain / (loss)', align: 'right', render: d => money(d.gain_loss) }, { key: 'journal', label: 'Journal', render: d => <JournalLink id={d.journal_id}>View journal</JournalLink> },
    ]} /> : <ListPanel<Asset> path="/assets/register/" search="Search tag, name, serial or location…" filters={[{ value: 'all', label: 'All' }, { value: 'active', label: 'Active', query: 'status=active' }, { value: 'disposed', label: 'Disposed', query: 'status=disposed' }]} columns={[
      { key: 'tag', label: 'Asset', render: a => <Primary mono title={a.tag} sub={a.name} href={`/assets/register/${a.id}`} /> }, { key: 'category', label: 'Category', render: a => a.category }, { key: 'service', label: 'In service', render: a => formatDate(a.in_service_date) }, { key: 'cost', label: 'Historical cost', align: 'right', render: a => money(a.cost) }, { key: 'dep', label: 'Accumulated', align: 'right', render: a => money(a.accumulated) }, { key: 'net', label: 'Book value', align: 'right', render: a => money(a.book_value) }, { key: 'status', label: 'Status', render: a => <StatusBadge status={a.status} /> },
    ]} />}
    {create && <RegisterDrawer onClose={() => setCreate(false)} />}
  </Screen>}</Gate>;
}
