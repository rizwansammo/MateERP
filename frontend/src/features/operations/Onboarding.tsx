'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Field } from '@/components/ui/Field';
import { InfoPanel } from '@/components/ui/InfoPanel';
import { useAccounts, useConfig } from '@/features/accounting/shared';
import type { Bank } from '@/features/accounting/types';
import { FormDrawer, Screen, body, type FieldSpec } from '@/features/commerce/forms';
import { Gate, ListPanel, Primary, StatusBadge, today, useApi, useMoney } from '@/features/commerce/shared';
import type { Vendor } from '@/features/commerce/types';
import { api } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import type { CatalogItem, Reference } from './types';

export interface HistoricalRecord {
  id: number;
  external_reference: string;
  original_date: string;
  description: string;
  currency: string;
  amount: string;
  payment_source: string;
  funding_classification: string;
  pre_registration: boolean;
  party_id: number | null;
  evidence_id: string | null;
  notes: string;
  treatment: { id: number; mode: string; recognition_date: string; reason: string; status: string;
    expense_id: number | null; vendor_bill_id: number | null; founder_transaction_id: string | null;
    journal_id: string | null; personal_settlement_id?: number | null } | null;
}

const classifications = [
  ['company_expense', 'Company-paid expense'], ['founder_expense', 'Founder-paid expenditure'],
  ['contribution', 'Contribution / pending funding'], ['loan', 'Founder loan'],
  ['reimbursement', 'Reimbursement'], ['personal_settlement', 'Personal founder settlement'],
  ['bank_balance', 'Prior bank balance'], ['vendor_payable', 'Outstanding vendor obligation'],
  ['inventory_opening', 'Prior inventory balance'],
].map(([value = '', label = '']) => ({ value, label }));

function DocumentDrawer({ onClose }: { onClose: () => void }) {
  const config = useConfig(); const { can } = useAuth();
  const parties = useApi<Page<{ id: number; name: string }>>(can('founder.view') ? '/founders/parties/?page_size=100' : null);
  const [file, setFile] = useState<File | null>(null);
  return <FormDrawer title="Document historical activity" eyebrow="Historical onboarding" width={680} onClose={onClose}
    initial={{ external_reference: '', original_date: '', description: '', currency: config.data?.base_currency ?? '', amount: '',
      payment_source: '', funding_classification: 'company_expense', pre_registration: false, party_id: '', notes: '' }}
    fields={[{ key: 'external_reference', label: 'Unique original reference', required: true, hint: 'Use the same source reference throughout cutover and reconstruction.' },
      { key: 'original_date', label: 'Original transaction date', type: 'date', required: true }, { key: 'description', label: 'Original description', required: true },
      { key: 'currency', label: 'Original currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) },
      { key: 'amount', label: 'Original amount', type: 'amount', required: true }, { key: 'payment_source', label: 'Original payment source / outstanding obligation', required: true },
      { key: 'funding_classification', label: 'Documented funding classification', type: 'select', options: classifications },
      ...(can('founder.view') ? [{ key: 'party_id', label: 'Founder / financial participant', type: 'select' as const, options: [{ value: '', label: 'Not applicable' }, ...(parties.data?.results ?? []).map(p => ({ value: String(p.id), label: p.name }))] }] : []),
      { key: 'pre_registration', label: 'Incurred before formal registration', type: 'checkbox' }, { key: 'notes', label: 'Evidence / legal and accounting context', type: 'textarea' }]}
    onSave={v => {
      if (!file) return api.post('/accounting/historical-records/', body(v));
      const form = new FormData();
      for (const [key, value] of Object.entries(v)) if (key !== 'party_id' || value) form.set(key, String(value));
      form.set('file', file);
      return api.post('/accounting/historical-records/', form);
    }}>
    <Field htmlFor="historical-evidence" label="Supporting document (PDF, PNG, JPEG or WEBP)"><Input id="historical-evidence" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)} /></Field>
    <Banner tone="info">This records evidence only. It creates no company expense, debt, capital or bank movement. Pre-registration payments require explicit authorized corporate adoption before recognition.</Banner>
  </FormDrawer>;
}

function TreatmentDrawer({ record, onClose }: { record: HistoricalRecord; onClose: () => void }) {
  const accounts = useAccounts(); const banks = useApi<Page<Bank>>('/banking/accounts/?page_size=100');
  const vendors = useApi<Page<Vendor>>('/purchasing/vendors/?page_size=100');
  const items = useApi<Page<CatalogItem>>('/catalog/items/?kind=stock&page_size=100');
  const locations = useApi<Page<Reference>>('/inventory/locations/?page_size=100');
  const [mode, setMode] = useState(['company_expense','founder_expense'].includes(record.funding_classification) ? 'reconstructed' : ['bank_balance','inventory_opening'].includes(record.funding_classification) ? 'opening_only' : 'linked');
  const [sourceSearch,setSourceSearch] = useState('');
  const sourcePath=record.funding_classification==='personal_settlement'?'/founders/settlements/':['contribution','loan','reimbursement','founder_expense'].includes(record.funding_classification)?'/founders/transactions/':record.funding_classification==='vendor_payable'?'/purchasing/bills/':'/purchasing/expenses/';
  const existing=useApi<Page<{id:number;number?:string;reference?:string;date?:string;expense_date?:string;bill_date?:string;amount?:string;total?:string;status:string}>>(mode==='linked'?`${sourcePath}?page_size=100&search=${encodeURIComponent(sourceSearch)}`:null);
  const bankOptions = [{ value: '', label: 'Choose original / cutover bank' }, ...(banks.data?.results ?? []).filter(b => b.is_active).map(b => ({ value: String(b.id), label: `${b.name} · ${b.currency}` }))];
  const fields: FieldSpec[] = [
    { key: 'mode', label: 'Accounting treatment', type: 'select', options: [
      ...(['company_expense','founder_expense'].includes(record.funding_classification)?[{value:'reconstructed',label:'Prepare the existing expense workflow'}]:[]),
      ...(['bank_balance','vendor_payable','founder_expense','loan','contribution','inventory_opening'].includes(record.funding_classification)?[{value:'opening_only',label:'Reviewed opening balance only'}]:[]),
      ...(!['bank_balance','inventory_opening'].includes(record.funding_classification)?[{value:'linked',label:'Link an existing independently verified source — no reposting'}]:[])] },
    { key: 'recognition_date', label: 'Permitted accounting recognition date', type: 'date', required: true },
    { key: 'reason', label: 'Authorized accounting / corporate adoption basis', type: 'textarea', required: true },
  ];
  if (mode === 'opening_only') fields.push(
    { key: 'opening_equity_account_id', label: 'Opening equity account', type: 'select', options: [{ value: '', label: 'Choose reviewed opening account' }, ...(accounts.data ?? []).filter(a => a.account_type === 'equity' && a.is_active && a.is_postable && !a.control).map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))] },
    { key: 'corporate_adoption_reference', label: 'Corporate adoption authority / evidence reference', required: record.pre_registration },
  );
  else if(mode==='reconstructed') fields.push(
    { key: 'account_id', label: 'Expense / acquisition account', type: 'select', options: [{ value: '', label: 'Choose account' }, ...(accounts.data ?? []).filter(a => ['expense', 'asset'].includes(a.account_type) && a.is_active && a.is_postable && !a.control).map(a => ({ value: String(a.id), label: `${a.code} · ${a.name}` }))] },
    { key: 'payment_mode', label: 'Company funding', type: 'select', options: [{ value: 'paid', label: 'Company-paid from documented bank' }, { value: 'accrued', label: 'Outstanding vendor obligation' }] },
    { key: 'classification', label: 'Founder corporate treatment (founder-paid only)', type: 'select', options: [{ value: 'pending', label: 'Pending funding classification' }, { value: 'payable', label: 'Approved reimbursement payable' }, { value: 'loan', label: 'Documented founder loan' }] },
  );
  if(mode==='linked') fields.push(
    {key:'source_search',label:'Find original source reference',hint:'Record and verify the original contribution, loan, reimbursement or settlement in its existing workflow first.'},
    {key:'source_id',label:'Existing verified source',type:'select',options:[{value:'',label:'Choose matching amount, currency and recognition date'},...(existing.data?.results??[]).filter(s=>['posted','partially_paid','paid','confirmed'].includes(s.status)).map(s=>({value:String(s.id),label:`${s.number??s.reference??`#${s.id}`} · ${s.date??s.expense_date??s.bill_date} · ${s.amount??s.total}`}))]},
    {key:'corporate_adoption_reference',label:'Corporate adoption authority / evidence reference',required:record.pre_registration&&record.funding_classification!=='personal_settlement'},
  );
  if (record.funding_classification === 'bank_balance' || (mode === 'reconstructed' && record.funding_classification === 'company_expense')) fields.push({ key: 'bank_id', label: 'Original / opening bank', type: 'select', options: bankOptions });
  if (record.funding_classification === 'vendor_payable' || mode === 'reconstructed') fields.push({ key: 'vendor_id', label: 'Vendor (required for accrued expenses)', type: 'select', options: [{ value: '', label: 'No vendor' }, ...(vendors.data?.results ?? []).map(v => ({ value: String(v.id), label: v.name }))] });
  if (record.funding_classification === 'inventory_opening') fields.push(
    { key: 'item_id', label: 'Opening tracked item', type: 'select', options: [{ value: '', label: 'Choose item' }, ...(items.data?.results ?? []).map(i => ({ value: String(i.id), label: i.name }))] },
    { key: 'location_id', label: 'Counted warehouse', type: 'select', options: [{ value: '', label: 'Choose location' }, ...(locations.data?.results ?? []).map(l => ({ value: String(l.id), label: l.name }))] },
    { key: 'quantity', label: 'Documented opening quantity', type: 'amount', required: true },
  );
  return <FormDrawer title="Request historical recognition review" eyebrow={record.external_reference} width={680} onClose={onClose}
    initial={{ mode, recognition_date: today(), reason: '', account_id: '', vendor_id: '', payment_mode: 'paid', bank_id: '',
      classification: 'pending', opening_equity_account_id: '', corporate_adoption_reference: '', item_id: '', location_id: '', quantity: '', source_id:'', source_search:'' }}
    fields={fields} onValues={v => {setMode(String(v.mode));setSourceSearch(String(v.source_search));}} saveLabel="Request independent review" success="Historical treatment submitted for independent review"
    onSave={v => {
      const payload = body(v); delete payload.mode; delete payload.recognition_date; delete payload.reason;
      delete payload.source_search;
      if (mode === 'reconstructed') { payload.bank_account_id = payload.bank_id; delete payload.bank_id; }
      return api.post(`/accounting/historical-records/${record.id}/treatment/`, { mode, recognition_date: v.recognition_date, reason: v.reason, payload });
    }}>
    <InfoPanel title="Original source (retained)" rows={[{ label: 'Original date', value: formatDate(record.original_date) }, { label: 'Funding', value: record.funding_classification }, { label: 'Payment source', value: record.payment_source }]} />
    <Banner tone="info">An independent authorized reviewer must approve. Reconstructed expenses remain drafts until the existing posting / founder verification workflow completes. Opening-only records do not repeat old expenses. Rates, periods and bank reconciliation restrictions remain enforced.</Banner>
  </FormDrawer>;
}

export function OnboardingPage() {
  const { can } = useAuth(); const money = useMoney(); const [create, setCreate] = useState(false); const [treatment, setTreatment] = useState<HistoricalRecord | null>(null);
  return <Gate allow={can('onboarding.manage') && can('finance.view')} what="reviewed historical onboarding"><Screen eyebrow="Purchases & Expenses" title="Historical Entry & Cutover"
    description="Document original activity one item at a time. Corporate recognition and opening balances require explicit independent review."
    actions={<Button variant="primary" icon="add" onClick={() => setCreate(true)}>Document historical activity</Button>}>
    <Banner tone="info">Recording startup expenditure creates no company liability. Use reconstruction for legitimate historical postings or a reviewed opening for prior balances. Each source receives one active disposition.</Banner>
    <ListPanel<HistoricalRecord> path="/accounting/historical-records/" title="Historical provenance" filters={[{ value: 'all', label: 'All' }, { value: 'reconstructed', label: 'Reconstructed', query: 'mode=reconstructed' }, { value: 'opening', label: 'Opening only', query: 'mode=opening_only' }]} columns={[
      { key: 'ref', label: 'Original source', render: r => <Primary title={r.external_reference} sub={r.description} /> },
      { key: 'date', label: 'Original date', render: r => formatDate(r.original_date) }, { key: 'funding', label: 'Funding', render: r => <Primary title={r.funding_classification} sub={r.pre_registration ? 'Pre-registration — no automatic corporate recognition' : r.payment_source} /> },
      { key: 'amount', label: 'Original amount', align: 'right', render: r => money(r.amount, r.currency) },
      { key: 'recognized', label: 'Recognition / provenance', render: r => r.treatment ? <Primary title={formatDate(r.treatment.recognition_date)} sub={r.treatment.mode} /> : 'Evidence only — no posting' },
      { key: 'status', label: 'Review', render: r => <StatusBadge status={r.treatment?.status ?? 'documented'} /> },
      { key: 'source', label: 'Financial record', render: r => r.treatment?.personal_settlement_id ? <Link href={`/founder/settlements/${r.treatment.personal_settlement_id}`}>Confirmed personal settlement</Link> : r.treatment?.expense_id ? <Link href={`/purchases/expenses/${r.treatment.expense_id}`}>Expense workflow</Link> : r.treatment?.vendor_bill_id ? <Link href={`/purchases/bills/${r.treatment.vendor_bill_id}`}>Payable source</Link> : r.treatment?.founder_transaction_id ? <Link href={`/founder/contributions/${r.treatment.founder_transaction_id}`}>Founder source</Link> : r.treatment?.journal_id ? <Link href={`/banking/journals/${r.treatment.journal_id}`}>Opening journal</Link> : '—' },
      { key: 'actions', label: 'Actions', render: r => <div className="flex gap-2">{r.evidence_id && <a href={`/api/v1/files/${r.evidence_id}/content/`} target="_blank" rel="noreferrer">Evidence</a>}{can('accounting.manage') && (!r.treatment || r.treatment.status === 'rejected') && <Button size="sm" onClick={() => setTreatment(r)}>Review treatment</Button>}{r.treatment?.status === 'pending' && <Link href="/settings/approvals">Approvals</Link>}</div> },
    ]} />
    {create && <DocumentDrawer onClose={() => setCreate(false)} />}{treatment && <TreatmentDrawer record={treatment} onClose={() => setTreatment(null)} />}
  </Screen></Gate>;
}
