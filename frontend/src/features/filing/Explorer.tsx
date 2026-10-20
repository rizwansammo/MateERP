'use client';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Icon } from '@/components/ui/Icon';
import { Input, Select } from '@/components/ui/Input';
import { Drawer } from '@/components/ui/Overlay';
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table';
import { Pager } from '@/components/ui/TableKit';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useDebounced } from '@/lib/useDebounced';
import { formatDate, formatDateTime } from '@/lib/format';
import { FormDrawer, Screen } from '@/features/commerce/forms';
import { FileViewer } from '@/features/commerce/FileViewer';
import { Gate, KIND_LABEL, KIND_ICON, act, useApi } from '@/features/commerce/shared';
import type { ClientTreeYear, VendorTreeYear, FiledDocument, DocumentKind } from '@/features/commerce/types';
import { UploadDrawer } from './UploadDrawer';

interface Folder { name: string; count: number; query: Record<string, string>; children: Folder[] }
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
export function clientFolders(years: ClientTreeYear[]): Folder[] {
  return years.map(y => ({ name: String(y.year), count: y.count, query: { year: String(y.year) }, children: y.clients.map(c => ({
    name: c.name, count: c.count, query: { year: String(y.year), customer: String(c.id) }, children: [
      ...c.invoices.map(i => ({ name: i.number || 'Unissued invoice', count: i.count, query: { year: String(y.year), customer: String(c.id), invoice: String(i.id) }, children: Object.entries(i.kinds).map(([kind, count]) => ({ name: KIND_LABEL[kind as DocumentKind], count: count ?? 0, query: { year: String(y.year), customer: String(c.id), invoice: String(i.id), kind }, children: [] })) })),
      ...Object.entries(c.other).map(([kind, count]) => ({ name: `${KIND_LABEL[kind as DocumentKind]} · other`, count: count ?? 0, query: { year: String(y.year), customer: String(c.id), unlinked: '1', kind }, children: [] })),
    ],
  })) }));
}
export function vendorFolders(years: VendorTreeYear[]): Folder[] {
  return years.map(y => ({ name: String(y.year), count: y.count, query: { year: String(y.year) }, children: y.months.map(m => ({ name: MONTHS[m.month - 1] ?? String(m.month), count: m.count, query: { year: String(y.year), month: String(m.month) }, children: m.vendors.map(v => ({ name: v.name, count: v.count, query: { year: String(y.year), month: String(m.month), vendor: String(v.id) }, children: Object.entries(v.kinds).map(([kind, count]) => ({ name: KIND_LABEL[kind as DocumentKind], count: count ?? 0, query: { year: String(y.year), month: String(m.month), vendor: String(v.id), kind }, children: [] })) })) })) }));
}
function matches(folder: Folder, params: URLSearchParams) { return Object.entries(folder.query).every(([k, v]) => params.get(k) === v); }
function branch(folders: Folder[], params: URLSearchParams): Folder[] {
  const selected = folders.find(f => matches(f, params)); return selected ? [selected, ...branch(selected.children, params)] : [];
}
function FolderTree({ folders, params, onSelect, depth = 0 }: { folders: Folder[]; params: URLSearchParams; onSelect: (f: Folder) => void; depth?: number }) {
  return folders.map(f => <div key={JSON.stringify(f.query)}><button type="button" onClick={() => onSelect(f)} className={`flex min-h-[34px] w-full items-center gap-2 border-l-2 py-2 pr-3 text-left text-[12px] hover:bg-sf3 ${matches(f, params) ? 'border-ac bg-infoS font-semibold text-tx' : 'border-transparent text-tx2'}`} style={{ paddingLeft: 12 + depth * 14 }}><Icon name={matches(f, params) ? 'folder_open' : 'folder'} size={17} className={matches(f, params) ? 'text-ac' : 'text-tx3'} /><span className="min-w-0 flex-1 truncate">{f.name}</span><span className="text-[11px] text-tx3">{f.count}</span></button>{matches(f, params) && <FolderTree folders={f.children} params={params} onSelect={onSelect} depth={depth + 1} />}</div>);
}
export function DocumentExplorer({ area }: { area: 'client' | 'vendor' }) {
  const { can } = useAuth();
  return <Gate allow={can('finance.view') || can(area === 'client' ? 'documents.client.view' : 'documents.vendor.view')} what={`${area} documents`}><Explorer area={area} /></Gate>;
}
function Explorer({ area }: { area: 'client' | 'vendor' }) {
  const { can } = useAuth(); const router = useRouter(); const current = useSearchParams(); const params = new URLSearchParams(current.toString()); const root = `/${area}-documents`;
  const [search, setSearch] = useState(''); const term = useDebounced(search, 250); const [order, setOrder] = useState('-document_date'); const [page, setPage] = useState(1); const [grid, setGrid] = useState(false); const [upload, setUpload] = useState(false);
  const [view, setView] = useState<FiledDocument | null>(null); const [detail, setDetail] = useState<FiledDocument | null>(null); const [archive, setArchive] = useState<FiledDocument | null>(null); const [editing, setEditing] = useState<FiledDocument | null>(null);
  const ct = useApi<ClientTreeYear[]>(area === 'client' ? '/documents/client-tree/' : null); const vt = useApi<VendorTreeYear[]>(area === 'vendor' ? '/documents/vendor-tree/' : null);
  const forest = area === 'client' ? clientFolders(ct.data ?? []) : vendorFolders(vt.data ?? []); const path = branch(forest, params); const active = path.at(-1); const folders = term || params.get('archived') === '1' ? [] : active?.children ?? forest;
  const query = term ? new URLSearchParams() : new URLSearchParams(params); query.set('area', area); query.set('page', String(page)); query.set('page_size', '25'); query.set('ordering', order); if (term) query.set('search', term); if (params.get('archived')) query.set('archived', '1');
  const docs = useApi<Page<FiledDocument>>(`/documents/?${query}`); const showFiles = Boolean(term || !folders.length || params.get('archived') === '1');
  const select = (folder?: Folder) => { setSearch(''); setPage(1); router.replace(folder ? `${root}?${new URLSearchParams(folder.query)}` : root, { scroll: false }); };
  const docActions = (d: FiledDocument) => <div className="flex flex-wrap justify-end gap-1"><Button size="xs" onClick={() => setView(d)}>Preview</Button><Button size="xs" onClick={() => setDetail(d)}>Details</Button><a href={d.download_url} className="px-2 py-1 text-[11.5px]">Download</a>{can('documents.manage') && !d.generated && !d.is_archived && <Button size="xs" onClick={() => setArchive(d)}>Archive</Button>}</div>;
  const loadError = docs.error || ct.error || vt.error;
  return <Screen eyebrow="Documents" title={area === 'client' ? 'Client Documents' : 'Vendor Documents'} description={area === 'client' ? 'Year → Client → Invoice → Document type. Official invoices and receipts are filed automatically; internal bank evidence remains restricted.' : 'Year → Month → Vendor → Invoices / Receipts. Files are organized from their financial links and document dates.'}
    actions={can('documents.manage') && <Button variant="primary" icon="upload_file" onClick={() => setUpload(true)}>Upload documents</Button>}
    meta={[{ label: 'Documents in view', value: String(docs.data?.count ?? '—') }, { label: 'Showing', value: term ? 'Search results' : active?.name ?? 'Years' }]}>
    {Boolean(loadError) && <Banner tone="err">{errorMessage(loadError)}</Banner>}
    <div className="flex min-h-[560px] flex-col border border-bd bg-sf">
      <div className="flex flex-wrap items-center gap-2.5 border-b border-bd px-3.5 py-2.5"><nav aria-label="Document folders" className="flex min-w-[200px] flex-1 flex-wrap items-center gap-1"><button onClick={() => select()} className="flex h-7 items-center gap-1 px-2 text-[12.5px]"><Icon name="home_storage" size={17} className="text-ac" />{area === 'client' ? 'Client Documents' : 'Vendor Documents'}</button>{path.map(f => <span key={JSON.stringify(f.query)} className="flex items-center"><Icon name="chevron_right" size={16} className="text-tx3" /><button type="button" className="h-7 px-2 text-[12.5px] hover:bg-sf3" onClick={() => select(f)}>{f.name}</button></span>)}</nav>
        <Input aria-label="Search documents" placeholder={`Search all ${area} documents…`} value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="!h-[30px] !w-[240px]" />
        <Select aria-label="Sort documents" value={order} onChange={e => { setOrder(e.target.value); setPage(1); }} className="!h-[30px] !w-[120px]"><option value="-document_date">Newest</option><option value="title">Name</option><option value="-created_at">Uploaded</option></Select>
        <Button size="sm" aria-label={grid ? 'List view' : 'Grid view'} icon={grid ? 'view_list' : 'grid_view'} onClick={() => setGrid(v => !v)} />
        {can('documents.manage') && <Button size="sm" onClick={() => { const next = new URLSearchParams(params); if (next.get('archived')) next.delete('archived'); else next.set('archived', '1'); router.replace(`${root}?${next}`, { scroll: false }); setPage(1); }}>{params.get('archived') ? 'Active files' : 'Include archived'}</Button>}
      </div>
      <div className="flex min-h-0 flex-1">
        <aside aria-label="Folder tree" className="hidden w-[250px] flex-none overflow-auto border-r border-bd bg-sf2 py-2 min-[1000px]:block"><FolderTree folders={forest} params={params} onSelect={select} /></aside>
        <div className="min-w-0 flex-1"><div className="border-b border-bd bg-sf2 px-4 py-2.5 text-[12px] text-tx3">{term ? 'Search covers authorized documents across all folders.' : active ? 'Folders are generated from saved document metadata and financial links.' : 'Year folders appear automatically when documents are filed.'}</div>
          {folders.length > 0 && <div className="grid grid-cols-[repeat(auto-fill,minmax(190px,1fr))] gap-3 p-4">{folders.map(f => <button type="button" key={JSON.stringify(f.query)} onClick={() => select(f)} className="flex items-center gap-3 border border-bd bg-sf p-4 text-left hover:border-ac hover:bg-sfh"><Icon name="folder" size={34} className={path.length === 0 ? 'text-[#E3A73B]' : 'text-ac'} /><span className="min-w-0"><span className="block truncate text-[13px] font-semibold">{f.name}</span><span className="text-[11.5px] text-tx3">{f.count} file(s)</span></span></button>)}</div>}
          {showFiles && (grid ? <div className="grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-3 p-4">{docs.data?.results.map(d => <div key={d.id} className="border border-bd p-3"><button type="button" onClick={() => setView(d)} className="mb-3 flex w-full flex-col items-center gap-2 bg-sf2 p-4"><Icon name={KIND_ICON[d.kind][0]} size={36} className={KIND_ICON[d.kind][1]} /><span className="max-w-full truncate font-semibold">{d.title}</span><span className="text-[11px] text-tx3">{KIND_LABEL[d.kind]} · {formatDate(d.document_date)}</span></button>{docActions(d)}</div>)}</div>
          : <Table><THead><TR><TH>Name</TH><TH>Type</TH><TH>Date</TH><TH>Size</TH><TH>Origin</TH><TH /></TR></THead><TBody>{docs.data?.results.map(d => <TR key={d.id}><TD><button type="button" onClick={() => setView(d)} className="flex items-center gap-2 text-left font-medium text-link"><Icon name={KIND_ICON[d.kind][0]} size={18} className={KIND_ICON[d.kind][1]} />{d.title}</button><div className="text-[11px] text-tx3">{d.customer_name ?? d.vendor_name}{d.is_archived ? ' · Archived' : ''}</div></TD><TD>{KIND_LABEL[d.kind]}{d.restricted && <div className="text-[11px] text-warn">Restricted</div>}</TD><TD>{formatDate(d.document_date)}</TD><TD>{Math.ceil(d.size / 1024)} KB</TD><TD>{d.generated ? 'MateERP' : 'Uploaded'}</TD><TD>{docActions(d)}</TD></TR>)}</TBody></Table>)}
          {showFiles && !docs.data?.count && <div className="flex flex-col items-center gap-2 p-12 text-center text-tx3"><Icon name={term ? 'search_off' : 'folder_off'} size={38} /><strong className="text-[16px] text-tx">{docs.loading ? 'Loading documents…' : term ? 'No matching documents' : 'This folder is empty'}</strong><span>Saved uploads and generated financial documents appear here automatically.</span></div>}
          {showFiles && docs.data && <Pager page={docs.data.page} totalPages={docs.data.total_pages} pageSize={docs.data.page_size} count={docs.data.count} onPage={setPage} />}
        </div>
      </div>
    </div>
    {upload && <UploadDrawer area={area} initial={{ ...(params.get('customer') ? { customer_id: params.get('customer')! } : {}), ...(params.get('vendor') ? { vendor_id: params.get('vendor')! } : {}), ...(params.get('invoice') ? { invoice_id: params.get('invoice')! } : {}), ...(params.get('kind') && !['invoice', 'receipt', 'credit_note'].includes(params.get('kind')!) ? { kind: params.get('kind')! } : {}) }} onClose={() => setUpload(false)} />}
    {view && <FileViewer doc={view} onClose={() => setView(null)} />}
    {detail && <DocumentDetails doc={detail} onClose={() => setDetail(null)} onEdit={() => { setEditing(detail); setDetail(null); }} />}
    {editing && <FormDrawer title="Edit document metadata" eyebrow="Documents" onClose={() => setEditing(null)} initial={{ title: editing.title, document_date: editing.document_date, notes: editing.notes }} fields={[{ key: 'title', label: 'Title', required: true }, { key: 'document_date', label: 'Document date', type: 'date' }, { key: 'notes', label: 'Notes', type: 'textarea' }]} onSave={v => api.patch(`/documents/${editing.id}/`, v)} />}
    <ConfirmDialog open={Boolean(archive)} title={`Archive ${archive?.title}?`} confirmLabel="Archive document" reason="required" onCancel={() => setArchive(null)} onConfirm={async reason => { await act(() => api.post(`/documents/${archive!.id}/archive/`, { reason }), 'Document archived; the private file is retained'); setArchive(null); }}>Archiving retains the file and audit history. Generated official PDFs cannot be archived.</ConfirmDialog>
  </Screen>;
}
function DocumentDetails({ doc: d, onClose, onEdit }: { doc: FiledDocument; onClose: () => void; onEdit: () => void }) {
  const { can } = useAuth();
  const links = [d.invoice_id && { href: `/sales/invoices/${d.invoice_id}`, title: d.invoice_number ?? 'Invoice' }, d.payment_id && { href: `/sales/payments/${d.payment_id}`, title: d.payment_number ?? 'Payment' }, d.receipt_id && { href: `/sales/receipts/${d.receipt_id}`, title: 'Official receipt' }, d.vendor_bill_id && { href: `/purchases/bills/${d.vendor_bill_id}`, title: d.bill_number ?? 'Vendor bill' }, d.expense_id && { href: `/purchases/expenses/${d.expense_id}`, title: d.expense_number ?? 'Expense' }, d.vendor_payment_id && { href: `/purchases/payments/${d.vendor_payment_id}`, title: 'Vendor payment' }].filter((link): link is { href: string; title: string } => Boolean(link));
  return <Drawer open title={d.title} eyebrow="Document metadata" onClose={onClose}><dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-x-4 gap-y-3 text-[12.5px]">{Object.entries({ Type: KIND_LABEL[d.kind], Party: d.customer_name ?? d.vendor_name ?? '', Date: formatDate(d.document_date), File: d.file_name, Format: d.content_type, Size: `${d.size} bytes`, Origin: d.generated ? 'Generated by MateERP' : d.uploaded_by ?? 'Upload', Created: formatDateTime(d.created_at), SHA256: d.sha256, Access: d.restricted ? 'Restricted banking evidence' : 'Authorized financial users', Notes: d.notes, Archive: d.is_archived ? d.archived_reason : 'Active' }).map(([label, value]) => <div key={label} className="contents"><dt className="text-tx3">{label}</dt><dd className="break-words">{value || '—'}</dd></div>)}</dl><div className="mt-5 flex flex-wrap gap-3">{links.map(l => <Link key={l.href} href={l.href}>{l.title}</Link>)}</div>{can('documents.manage') && !d.generated && !d.is_archived && <Button className="mt-5" onClick={onEdit}>Edit metadata</Button>}</Drawer>;
}
