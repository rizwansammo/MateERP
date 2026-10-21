'use client';
import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Input, Select } from '@/components/ui/Input';
import { MonthlyChart, BreakdownChart } from '@/features/commerce/Charts';
import { StatGrid } from '@/components/ui/StatGrid';
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table';
import { Screen, FormDrawer, body } from '@/features/commerce/forms';
import { Card, ListPanel, Primary, StatusBadge, useApi, useMoney } from '@/features/commerce/shared';
import { useConfig } from '@/features/accounting/shared';
import { api, errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { minor } from '@/features/accounting/money';
import type { FounderOverview, Loan } from './types';
import { label, partyOptions, useParties } from './shared';
import { CorporateDrawer } from './Corporate';
import { PartyDrawer } from './Parties';

export function FounderOverviewPage({statement=false}:{statement?:boolean}) {
  const [from,setFrom]=useState(''); const [to,setTo]=useState('');
  const statementParams=new URLSearchParams();
  if(from) statementParams.set('from',from); if(to) statementParams.set('to',to);
  const {can}=useAuth(); const config=useConfig(); const money=useMoney(); const [selected,setSelected]=useState(''); const parties=useParties();
  const query=useApi<FounderOverview>(`/founders/overview/${selected ? `?party_id=${selected}` : ''}`);
  const [create,setCreate]=useState(false); const [participant,setParticipant]=useState(false);
  if(selected) statementParams.set('party_id',selected);
  return <Screen eyebrow="Founder Finance" title={statement ? 'Founder statements' : 'Founder finance overview'} description="Company capital, liabilities and verified funding. Personal sharing is shown in its own records and never silently changes these company balances." actions={<div className="flex gap-2">{can('founder.transactions.manage') && <><Button onClick={()=>setParticipant(true)}>Add founder</Button><Button variant="primary" onClick={()=>setCreate(true)}>Record contribution</Button></>}<Link href="/banking/coa">Configure posting controls</Link></div>}>
    {Boolean(query.error) && <Banner tone="err">{errorMessage(query.error)}</Banner>}
    <div className="flex flex-wrap items-center gap-3"><Select aria-label="Founder statement" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">All founders</option>{parties.data?.results.filter(p=>p.is_founder).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</Select>{can('founder.personal.view') && <Link href="/founder/settlements">Open separate personal settlement balances</Link>}</div>
    <StatGrid minWidth={180} stats={(query.data?.reconciliation ?? []).map(r=>({label:label(r.category),value:money(r.source_balance,config.data?.base_currency),sub:'Company source balance · base currency',accentBar:true}))}/>
    {!statement && <div className="grid gap-[18px] lg:grid-cols-2"><MonthlyChart title="Founder company activity" subtitle="Historical base valuation · current year · source reversals included" points={query.data?.monthly} series={[{key:'receipts',label:'Company receipts'},{key:'funded_costs',label:'Personally funded'},{key:'repayments',label:'Principal / reimbursements'}]} currency={config.data?.base_currency}/><BreakdownChart title="Founder company balances" subtitle="Independent source balances · base currency" rows={query.data?.reconciliation.map(r=>({label:label(r.category),amount:r.source_balance}))} currency={config.data?.base_currency}/></div>}
    {statement && <><div className="flex flex-wrap gap-3"><Input aria-label="Statement from date" type="date" value={from} onChange={e=>setFrom(e.target.value)}/><Input aria-label="Statement through date" type="date" value={to} onChange={e=>setTo(e.target.value)}/>{can('reports.export') && <a href={`/api/v1/founders/statements/?${statementParams}&export=csv`}>Export company statement CSV</a>}</div><ListPanel<FounderStatementLine> path={`/founders/statements/?${statementParams}`} search={false} title="Corporate control statement" subtitle="Running balances include earlier posted activity. Each control, party and currency has its own balance; personal transfers are separate." columns={[{key:'date',label:'Date',render:r=>r.date},{key:'party',label:'Participant',render:r=>r.party},{key:'control',label:'Control / currency',render:r=>`${r.control} · ${r.currency}`},{key:'debit',label:'Debit',align:'right',render:r=>money(r.debit,r.currency)},{key:'credit',label:'Credit',align:'right',render:r=>money(r.credit,r.currency)},{key:'balance',label:'Balance',align:'right',render:r=>money(r.balance,r.currency)},{key:'number',label:'Journal',render:r=><Link href={`/banking/journals/${r.journal}`}>{r.number}</Link>}]}/></>}
    <div className="grid gap-[18px] lg:grid-cols-2">{query.data?.founders.map(f=><Card key={f.id} title={f.name} subtitle={f.is_active ? 'Active participant' : 'Historical participant'}><div className="divide-y divide-bd px-4">{f.obligations.map(o=><div key={o.id} className="flex justify-between gap-3 py-2"><span className="text-tx3">{label(o.category)} · #{o.id}</span><span className="tabular-nums">{money(o.outstanding,o.currency)}</span></div>)}{!f.obligations.length && <p className="py-4 text-tx3">No posted company obligations.</p>}</div></Card>)}</div>
    {query.data && !query.data.founders.length && <Card title="No founders configured"><p className="p-4 text-tx3">Add actual participants to begin. No sample founders or balances have been seeded.</p></Card>}
    <Card title={statement ? 'Company transactions by founder' : 'Recent founder transactions'} subtitle="Recorded, approved and posted states remain distinct. Open a source for its journal and private evidence."><Table><THead><TR><TH>Date</TH><TH>Founder</TH><TH>Event</TH><TH>Treatment</TH><TH>Status</TH><TH>Journal</TH><TH align="right">Amount</TH></TR></THead><TBody>{query.data?.founders.flatMap(f=>f.events.map(e=><TR key={e.id}><TD>{e.date}</TD><TD>{f.name}</TD><TD><Link href={`/founder/contributions/${e.id}`}>{label(e.kind)} #{e.id}</Link></TD><TD>{label(e.classification)}</TD><TD><StatusBadge status={e.status}/></TD><TD>{e.journal_number || 'Not posted'}</TD><TD align="right">{money(e.amount,e.currency)}</TD></TR>))}{query.data?.founders.every(f=>!f.events.length) && <TR><TD colSpan={7}>No transactions recorded.</TD></TR>}</TBody></Table></Card>
    <Card title="Independent company reconciliation"><Table><THead><TR><TH>Control</TH><TH align="right">Source balance</TH><TH align="right">General ledger</TH><TH align="right">Difference</TH></TR></THead><TBody>{query.data?.reconciliation.map(r=><TR key={r.category}><TD>{label(r.category)}</TD><TD align="right">{money(r.source_balance,config.data?.base_currency)}</TD><TD align="right">{money(r.gl_balance,config.data?.base_currency)}</TD><TD align="right"><span className={minor(r.difference)!==0n ? 'text-err' : 'text-ok'}>{money(r.difference,config.data?.base_currency)}</span></TD></TR>)}</TBody></Table></Card>
    {participant && <PartyDrawer onClose={()=>setParticipant(false)}/>}{create && <CorporateDrawer kind="receipt" onClose={()=>setCreate(false)}/>}
  </Screen>;
}

interface FounderStatementLine {id:number;date:string;party:string;control:string;currency:string;debit:string;credit:string;balance:string;journal:string;number:string}

export function LoansPage() {
  const {can}=useAuth(); const parties=useParties(); const config=useConfig(); const [newLoan,setNewLoan]=useState(false); const [transaction,setTransaction]=useState<string|null>(null);
  return <Screen eyebrow="Founder Finance" title="Founder loans" description="Documented principal agreements, verified drawdowns and exact partial repayments. Loan principal is neither revenue nor operating expense." actions={can('founder.transactions.manage') && <div className="flex gap-2"><Button onClick={()=>setTransaction('loan_repayment')}>Repay principal</Button><Button onClick={()=>setTransaction('receipt')}>Record drawdown</Button><Button variant="primary" onClick={()=>setNewLoan(true)}>New loan agreement</Button></div>}>
    <Banner tone="info">Terms may describe interest, but Phase 5 does not automatically accrue interest or calculate related taxes.</Banner>
    <ListPanel<Loan> path="/founders/loans/" columns={[{key:'loan',label:'Agreement',render:l=><Primary title={l.name} sub={l.reference}/>},{key:'party',label:'Lender',render:l=>parties.data?.results.find(p=>p.id===l.party)?.name ?? `Participant #${l.party}`},{key:'currency',label:'Currency',render:l=>l.currency},{key:'maturity',label:'Maturity',render:l=>l.maturity || 'As agreed'},{key:'terms',label:'Terms',render:l=>l.terms},{key:'status',label:'Status',render:l=>l.is_active ? 'Active' : 'Inactive'}]}/>
    <p className="text-[12px] text-tx3">Outstanding principal and posted repayments appear in <Link href="/founder/statements">Founder Statements</Link>.</p>
    {newLoan && <FormDrawer title="Founder loan agreement" eyebrow="Corporate liability terms" onClose={()=>setNewLoan(false)} initial={{name:'',party_id:'',currency:config.data?.base_currency ?? '',terms:'',maturity:'',reference:''}} fields={[{key:'name',label:'Agreement name',required:true},{key:'party_id',label:'Founder lender',type:'select',options:partyOptions(parties.data?.results.filter(p=>p.is_founder)),required:true},{key:'currency',label:'Currency',type:'select',options:(config.data?.enabled_currencies ?? []).map(value=>({value,label:value}))},{key:'maturity',label:'Maturity (optional)',type:'date'},{key:'reference',label:'Agreement reference'},{key:'terms',label:'Terms',type:'textarea'}]} onSave={v=>api.post('/founders/loans/',{...body(v),maturity:v.maturity || null})}/>}
    {transaction && <CorporateDrawer kind={transaction} onClose={()=>setTransaction(null)}/>}
  </Screen>;
}
