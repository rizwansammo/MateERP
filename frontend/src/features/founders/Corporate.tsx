'use client';
import Link from 'next/link';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Banner } from '@/components/ui/Banner';
import { Checkbox } from '@/components/ui/Choice';
import { Field } from '@/components/ui/Field';
import { AmountInput } from '@/components/ui/Input';
import { FormDrawer, Screen, body, type FormValues } from '@/features/commerce/forms';
import { act, Card, ListPanel, Primary, StatusBadge, useActionKey, useApi, useMoney, today } from '@/features/commerce/shared';
import { useAccounts, useConfig } from '@/features/accounting/shared';
import { postingAccounts, useTaxCodes } from '@/features/commerce/lines';
import { FileViewer, type PrivateDocumentView } from '@/features/commerce/FileViewer';
import { api, errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import type { Page } from '@/lib/api/types';
import type { Bank } from '@/features/accounting/types';
import type { Bill, Expense } from '@/features/commerce/types';
import type { CorporateTransaction, FinancialQuote, Loan, Obligation, StoredEvidence } from './types';
import { EvidenceDrawer, EvidenceList, QuoteTable, label, partyOptions, useParties } from './shared';

export function CorporateDrawer({kind,onClose,partyId}:{kind:string;onClose:()=>void;partyId?:number}) {
  const parties=useParties(); const config=useConfig(); const accounts=useAccounts(); const taxes=useTaxCodes(); const actionKey=useActionKey();
  const banks=useApi<Page<Bank>>('/banking/accounts/?page_size=100'); const loans=useApi<Page<Loan>>('/founders/loans/?page_size=100'); const obligations=useApi<Page<Obligation>>('/founders/obligations/?page_size=100');
  const bills=useApi<Page<Bill>>(kind==='vendor_payment' ? '/purchasing/bills/?page_size=100' : null); const expenses=useApi<Page<Expense>>(kind==='vendor_payment' ? '/purchasing/expenses/?page_size=100' : null);
  const [allocations,setAllocations]=useState<Record<string,string>>({}); const money=useMoney();
  const isOut=['reimbursement','loan_repayment','reclassify','reassign'].includes(kind); const isExpense=kind==='expense';
  const fields = [
    {key:'party_id',label:'Founder / shareholder',type:'select' as const,options:partyOptions(parties.data?.results.filter(p=>p.is_founder || (kind==='receipt' && p.is_shareholder))),required:true}, {key:'date',label:'Business date',type:'date' as const,required:true},
    {key:'currency',label:'Currency',type:'select' as const,options:(config.data?.enabled_currencies ?? []).map(value=>({value,label:value})),required:true},
    {key:'amount',label:isExpense ? 'Expense amount' : 'Amount',type:'amount' as const,required:true},
    ...(!['reimbursement','loan_repayment'].includes(kind) ? [{key:'classification',label:'Company accounting treatment',type:'select' as const,options:(isExpense || kind==='vendor_payment' ? ['payable','loan','other_equity'] : ['pending','loan','other_equity','share_capital']).map(value=>({value,label:label(value)}))}] : []),
    ...(['receipt','reimbursement','loan_repayment'].includes(kind) ? [{key:'bank_id',label:'Company bank / cash account',type:'select' as const,options:[{value:'',label:'Select company account…'},...(banks.data?.results ?? []).map(b=>({value:String(b.id),label:`${b.name} · ${b.currency}`}))]}] : []),
    ...(!['reimbursement','loan_repayment'].includes(kind) ? [{key:'loan_id',label:'Loan agreement (for loan classification)',type:'select' as const,options:[{value:'',label:'Not a loan'},...(loans.data?.results ?? []).map(l=>({value:String(l.id),label:`${l.name} · ${l.currency}`}))]},{key:'issuance_id',label:'Confirmed issuance ID (share capital only)',type:'number' as const}] : []),
    ...(kind==='reassign' ? [{key:'recipient_id',label:'New company creditor',type:'select' as const,options:partyOptions(parties.data?.results)}] : []),
    ...(isExpense ? [{key:'description',label:'Business expense description',required:true},{key:'account_id',label:'Expense / asset account',type:'select' as const,options:[{value:'',label:'Select…'},...postingAccounts(accounts.data,'expense').map(a=>({value:String(a.id),label:`${a.code} · ${a.name}`}))]},{key:'tax_code_id',label:'Tax code',type:'select' as const,options:[{value:'',label:'No tax'},...(taxes.data?.results ?? []).map(t=>({value:String(t.id),label:t.code}))]},{key:'prices_include_tax',label:'Amount includes tax',type:'checkbox' as const}] : []),
    {key:'reference',label:'Payment / agreement reference'},{key:'notes',label:'Notes / justification',type:'textarea' as const},
  ];
  const save = (v:FormValues) => {
    const payload=body(v); for(const key of ['loan_id','issuance_id','recipient_id','bank_id']) if(payload[key]===null) delete payload[key];
    if(isExpense){ payload.expense={description:v.description,account_id:Number(v.account_id),amount:v.amount,tax_code_id:v.tax_code_id ? Number(v.tax_code_id) : null,prices_include_tax:v.prices_include_tax}; for(const key of ['description','account_id','tax_code_id','prices_include_tax']) delete payload[key]; }
    if(isOut) payload.allocations=Object.entries(allocations).filter(([,amount])=>amount).map(([id,amount])=>({obligation_id:Number(id),amount}));
    if(kind==='vendor_payment') payload.vendor_allocations=Object.entries(allocations).filter(([,amount])=>amount).map(([id,amount])=>({[id.startsWith('bill:') ? 'bill_id' : 'expense_id']:Number(id.split(':')[1]),amount}));
    return api.post<CorporateTransaction>('/founders/transactions/',{...payload,kind,client_key:actionKey.key});
  };
  return <FormDrawer title={label(kind)} eyebrow="Founder Finance" width={820} onClose={onClose} success="Recorded for independent verification" initial={{party_id:String(partyId ?? ''),date:today(),currency:config.data?.base_currency ?? '',amount:'',classification:kind==='loan_repayment' ? 'loan' : kind==='reimbursement' || isExpense || kind==='vendor_payment' ? 'payable' : 'pending',bank_id:'',loan_id:'',issuance_id:'',recipient_id:'',reference:'',notes:'',description:'',account_id:'',tax_code_id:'',prices_include_tax:false}} fields={fields} extraDirty={Object.values(allocations).some(Boolean)} onSave={save}>
    {v=><><Banner tone="info">Recording does not post money. Another authorized user must verify the source, exact allocations and accounting preview. Personal transfers belong in Settlements.</Banner>
      {isOut && <div className="mt-4"><h3 className="mb-2 font-semibold">Company obligations to settle</h3>{(obligations.data?.results ?? []).filter(o=>o.party_id===Number(v.party_id) && o.currency===v.currency && (kind==='reimbursement' ? o.category==='payable' : kind==='loan_repayment' ? o.category==='loan' : true)).map(o=><Field key={o.id} htmlFor={`obligation-${o.id}`} label={`#${o.id} · ${label(o.category)} · ${money(o.outstanding,o.currency)} remaining`}><AmountInput id={`obligation-${o.id}`} aria-label={`Allocate obligation ${o.id}`} value={allocations[String(o.id)] ?? ''} onChange={e=>setAllocations({...allocations,[String(o.id)]:e.target.value})}/></Field>)}</div>}
      {kind==='vendor_payment' && <div className="mt-4"><h3 className="mb-2 font-semibold">Posted bills / accrued expenses paid personally</h3>{[...(bills.data?.results ?? []).filter(b=>['posted','partially_paid'].includes(b.status)).map(b=>({id:`bill:${b.id}`,label:b.number ?? `Bill ${b.id}`,amount:b.outstanding,currency:b.currency})),...(expenses.data?.results ?? []).filter(e=>e.payment_mode==='accrued' && ['posted','partially_paid'].includes(e.status)).map(e=>({id:`expense:${e.id}`,label:e.number ?? `Expense ${e.id}`,amount:e.outstanding,currency:e.currency}))].filter(source=>source.currency===v.currency).map(source=><Field key={source.id} htmlFor={`vendor-${source.id}`} label={`${source.label} · ${money(source.amount,source.currency)} remaining`}><AmountInput id={`vendor-${source.id}`} aria-label={`Allocate ${source.label}`} value={allocations[source.id] ?? ''} onChange={e=>setAllocations({...allocations,[source.id]:e.target.value})}/></Field>)}</div>}
    </>}
  </FormDrawer>;
}

export function CorporatePage({section}:{section:string}) {
  const {can}=useAuth(); const money=useMoney(); const [create,setCreate]=useState<string|null>(null);
  const kind=section==='expenses' ? 'expense' : section==='reimbursements' ? 'reimbursement' : 'receipt';
  return <Screen eyebrow="Founder Finance" title={section==='contributions' ? 'Founder contributions' : section==='expenses' ? 'Founder-paid expenses' : 'Company reimbursements'} description="Corporate source records and exact liabilities. Pending verification has no ledger effect; personal settlements remain separate." actions={can('founder.transactions.manage') && <div className="flex flex-wrap gap-2"><Button onClick={()=>setCreate('reclassify')}>Reclassify funding</Button>{section==='expenses' && <Button onClick={()=>setCreate('vendor_payment')}>Founder paid existing bill</Button>}<Button variant="primary" onClick={()=>setCreate(kind)}>{label(kind)}</Button></div>}>
    {section==='reimbursements' && <Banner tone="warn">Overlapping personal recovery blocks reimbursement until an authorized resolution is recorded. A personal transfer never reduces company debt automatically.</Banner>}
    <ListPanel<CorporateTransaction> path={`/founders/transactions/?kind=${kind}`} columns={[
      {key:'ref',label:'Reference',render:t=><Primary href={`/founder/${section}/${t.id}`} title={t.reference || `Founder transaction #${t.id}`} sub={t.date}/>}, {key:'party',label:'Founder',render:t=>t.party_name}, {key:'classification',label:'Treatment',render:t=>label(t.classification)}, {key:'status',label:'Status',render:t=><StatusBadge status={t.status}/>}, {key:'amount',label:'Amount',align:'right',render:t=>money(t.amount,t.currency)},
    ]}/>{section==='expenses' && <ListPanel<CorporateTransaction> path="/founders/transactions/?kind=vendor_payment" title="Vendor bills settled personally" columns={[{key:'ref',label:'Record',render:t=><Primary href={`/founder/expenses/${t.id}`} title={t.reference || `#${t.id}`} sub={t.party_name}/>},{key:'status',label:'Status',render:t=><StatusBadge status={t.status}/>},{key:'amount',label:'Amount',align:'right',render:t=>money(t.amount,t.currency)}]}/>}
    {create && <CorporateDrawer kind={create} onClose={()=>setCreate(null)}/>}
  </Screen>;
}

export function CorporateDetail({id}:{id:string}) {
  const [rejection,setRejection]=useState(false);
  const {can,user}=useAuth(); const query=useApi<CorporateTransaction>(`/founders/transactions/${id}/`); const evidences=useApi<Page<StoredEvidence>>(`/founders/evidence/?transaction_id=${id}`); const parties=useParties();
  const [quote,setQuote]=useState<FinancialQuote|null>(null); const [accepted,setAccepted]=useState(false); const [error,setError]=useState<string|null>(null); const [busy,setBusy]=useState(false); const [upload,setUpload]=useState(false); const [file,setFile]=useState<PrivateDocumentView|null>(null); const [reversal,setReversal]=useState(false);
  const tx=query.data; const money=useMoney(); const run=async(action:()=>Promise<unknown>,message:string)=>{if(busy)return;setBusy(true);setError(null);try{await act(action,message);}catch(e){setError(errorMessage(e));}finally{setBusy(false);}};
  return <Screen eyebrow="Founder corporate transaction" title={tx ? `${label(tx.kind)} #${tx.id}` : 'Loading transaction…'} description={tx ? `${tx.party_name} · ${tx.date} · ${label(tx.classification)}` : ''} actions={<div className="flex gap-2">{can('founder.transactions.manage') && <Button onClick={()=>setUpload(true)}>Attach evidence</Button>}{tx?.status==='posted' && can('founder.liabilities.manage') && can('founder.verify') && <Button onClick={()=>setReversal(true)}>Reverse</Button>}</div>}>
    {Boolean(error || query.error) && <Banner tone="err">{error ?? errorMessage(query.error)}</Banner>}
    {tx && <Card title="Recorded source"><div className="grid gap-3 p-4 sm:grid-cols-3"><div><span className="text-tx3">Amount</span><strong className="block text-[20px]">{money(tx.amount,tx.currency)}</strong></div><div><span className="text-tx3">Status</span><div><StatusBadge status={tx.status}/></div></div><div><span className="text-tx3">Journal</span><div>{tx.journal ? <Link href={`/banking/journals/${tx.journal}`}>Open journal #{tx.journal}</Link> : 'Not posted'}</div></div><div className="sm:col-span-3 text-tx2">{tx.notes || 'No additional notes.'}</div></div></Card>}
    {tx?.status==='recorded' && <Card title="Independent verification"><div className="flex flex-col gap-3 p-4"><Banner tone="info">The recorder cannot verify this transaction. Review source evidence and the current accounting preview.</Banner><Button disabled={busy} onClick={()=>void run(async()=>{setQuote(await api.post<FinancialQuote>(`/founders/transactions/${id}/preview/`,{}));},'Accounting preview updated')}>Preview accounting</Button>{quote && <><QuoteTable quote={quote}/><Checkbox label="I reviewed the disclosed FX and source allocations" checked={accepted} onChange={setAccepted}/>{can('founder.verify') && user.id!==tx.created_by && <Button variant="primary" disabled={!accepted || busy} onClick={()=>void run(()=>api.post(`/founders/transactions/${id}/verify/`,{quote_fingerprint:quote.quote_fingerprint,confirm_fx:accepted}),'Verification processed')}>Verify transaction</Button>}</>}</div></Card>}
    {tx?.status==='awaiting_approval' && <Banner tone="warn">Awaiting approval #{tx.approval}. No financial posting has occurred. <Link href="/settings/approvals">Review approvals</Link></Banner>}
    {tx?.status==='recorded' && can('founder.transactions.manage') && (tx.created_by===user.id || can('founder.verify')) && <Button variant="danger" onClick={()=>setRejection(true)}>Reject recorded transaction</Button>}
    {rejection && <FormDrawer title="Reject recorded founder transaction" eyebrow="No financial posting" initial={{reason:''}} fields={[{key:'reason',label:'Reason',type:'textarea',required:true}]} onSave={v=>api.post(`/founders/transactions/${id}/reject/`,v)} onClose={()=>setRejection(false)}/>}
    {tx?.snapshot.quote && <QuoteTable quote={tx.snapshot.quote}/>}
    <EvidenceList items={evidences.data?.results ?? []} onView={f=>setFile({...f,title:f.original_name,download_url:`${f.url}?download=1`,document_date:tx?.date ?? today(),label:'Founder corporate evidence'})}/>
    {upload && <EvidenceDrawer target={{transaction_id:Number(id)}} parties={parties.data?.results} onClose={()=>setUpload(false)}/>}{file && <FileViewer doc={file} onClose={()=>setFile(null)}/>}
    {reversal && <FormDrawer title="Reverse founder transaction" eyebrow="Traceable correction" initial={{date:today(),reason:''}} fields={[{key:'date',label:'Reversal date',type:'date'},{key:'reason',label:'Reason',type:'textarea',required:true}]} onSave={v=>api.post(`/founders/transactions/${id}/reverse/`,v)} onClose={()=>setReversal(false)}/>}
  </Screen>;
}
