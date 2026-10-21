'use client';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Input, AmountInput } from '@/components/ui/Input';
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table';
import { FormDrawer } from '@/features/commerce/forms';
import { Card, useApi, useMoney } from '@/features/commerce/shared';
import { useAccounts } from '@/features/accounting/shared';
import { api } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import type { Party, StoredEvidence, FinancialQuote } from './types';

export function useParties() { return useApi<Page<Party>>('/founders/parties/?page_size=100'); }
export const labels: Record<string,string> = {receipt:'Company receipt', expense:'Founder-paid expense', vendor_payment:'Vendor bill paid personally', reimbursement:'Company reimbursement', loan_repayment:'Loan principal repayment', reclassify:'Funding reclassification', reassign:'Liability reassignment', payable:'Reimbursable founder payable', loan:'Founder loan', other_equity:'Other contributed equity', share_capital:'Paid-in share capital', pending:'Pending classification'};
export const label = (key:string) => labels[key] ?? key.replaceAll('_',' ');
export const partyOptions = (parties?: Party[]) => [{value:'',label:'Select participant…'}, ...(parties ?? []).map(p => ({value:String(p.id),label:p.display_name || p.name}))];

export function WeightEditor({ parties, values, onChange, equal = false }: { parties:Party[]; values:Record<string,string>; onChange:(values:Record<string,string>)=>void; equal?:boolean }) {
  return <div className="overflow-x-auto border border-bd"><Table><THead><TR><TH>Participant</TH><TH>{equal ? 'Included' : 'Percentage'}</TH></TR></THead><TBody>{parties.map(p => <TR key={p.id}><TD>{p.name}</TD><TD>{equal ? <input type="checkbox" aria-label={`Include ${p.name}`} checked={String(p.id) in values} onChange={e => {const next={...values}; if(e.target.checked) next[String(p.id)]='1'; else delete next[String(p.id)]; onChange(next);}} /> : <AmountInput aria-label={`${p.name} percentage`} value={values[String(p.id)] ?? ''} onChange={e => {const next={...values}; if(e.target.value) next[String(p.id)]=e.target.value; else delete next[String(p.id)]; onChange(next);}} />}</TD></TR>)}</TBody></Table></div>;
}

export function QuoteTable({ quote }: {quote:FinancialQuote}) {
  const accounts = useAccounts(); const money=useMoney();
  return <Card title="Reviewed company accounting" subtitle="Only a verified and approved action posts these entries."><Table><THead><TR><TH>Account</TH><TH>Currency</TH><TH align="right">Debit</TH><TH align="right">Credit</TH><TH align="right">Base debit</TH><TH align="right">Base credit</TH></TR></THead><TBody>{quote.lines.map((l,i)=><TR key={i}><TD>{accounts.data?.find(a=>a.id===l.account_id)?.name ?? `GL ${l.account_id}`}</TD><TD>{l.currency}</TD><TD align="right">{money(l.debit,l.currency)}</TD><TD align="right">{money(l.credit,l.currency)}</TD><TD align="right">{money(l.base_debit,quote.base_currency)}</TD><TD align="right">{money(l.base_credit,quote.base_currency)}</TD></TR>)}</TBody></Table><div className="border-t border-bd p-3 text-[12px]">Disclosed FX difference: {money(quote.fx_difference,quote.base_currency)}</div></Card>;
}

export function EvidenceDrawer({ target, parties, onClose }: {target:{proposal_id?:number;transaction_id?:number;settlement_id?:number;loan_id?:number;party_id?:number};parties?:Party[];onClose:()=>void}) {
  const [file,setFile]=useState<File|null>(null);
  return <FormDrawer title="Attach private evidence" eyebrow="Authorization & supporting documents" initial={{title:'',party_id:String(target.party_id ?? '')}} fields={[{key:'title',label:'Document title',required:true},{key:'party_id',label:'Participant authorization relates to',type:'select',options:partyOptions(parties),hint:'Select the affected participant for an external-party attestation.'}]} onClose={onClose} extraDirty={Boolean(file)} success="Private evidence retained" onSave={async v=>{
    if(!file) throw new Error('Choose a PDF, PNG, JPEG or WEBP file.');
    const data=new FormData(); data.set('file',file); data.set('title',String(v.title)); for(const [key,value] of Object.entries(target)) if(value) data.set(key,String(value)); if(v.party_id) data.set('party_id',String(v.party_id));
    return api.post('/founders/evidence/',data);
  }}><div className="mt-4 border border-dashed border-bd2 p-4" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();setFile(e.dataTransfer.files[0] ?? null);}}><Field label="File" htmlFor="founder-evidence" hint="Private PDF or approved image, up to 10 MB. Attach all authorization evidence before confirmations."><Input id="founder-evidence" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={e=>setFile(e.target.files?.[0] ?? null)}/></Field>{file && <div className="mt-2 text-tx3">{file.name}</div>}</div></FormDrawer>;
}

export function EvidenceList({items,onView}:{items:StoredEvidence[];onView:(file:StoredEvidence['file'])=>void}) {
  return <Card title="Private supporting documents"><div className="divide-y divide-bd">{items.length ? items.map(item=><div key={item.id} className="flex items-center justify-between gap-3 px-4 py-3"><div><strong>{item.title}</strong><div className="text-[11px] text-tx3">{item.file.original_name}</div></div><Button size="sm" onClick={()=>onView(item.file)}>Preview</Button></div>) : <div className="p-4 text-tx3">No supporting documents attached.</div>}</div></Card>;
}
