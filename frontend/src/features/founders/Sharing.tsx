'use client';
import { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Banner } from '@/components/ui/Banner';
import { Segmented } from '@/components/ui/Choice';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { act, Gate, ListPanel, Primary, StatusBadge, useApi, useMoney, today } from '@/features/commerce/shared';
import { api, errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useAccounts, useConfig } from '@/features/accounting/shared';
import { postingAccounts } from '@/features/commerce/lines';
import type { Page } from '@/lib/api/types';
import type { CorporateTransaction, Policy, SharedExpense } from './types';
import { partyOptions, useParties, WeightEditor } from './shared';
import { PlannerPageContent, ReserveContent, ContributionContent } from './Planning';

function PolicyDrawer({onClose}:{onClose:()=>void}) {
  const parties=useParties(); const accounts=useAccounts(); const [weights,setWeights]=useState<Record<string,string>>({});
  return <FormDrawer title="New expense-sharing policy" eyebrow="Effective-dated allocation" initial={{name:'',effective_from:today(),effective_until:'',basis:'equal',category_id:''}} fields={[{key:'name',label:'Policy name',required:true},{key:'effective_from',label:'Effective from',type:'date'},{key:'effective_until',label:'Effective until (optional)',type:'date'},{key:'basis',label:'Allocation basis',type:'select',options:[{value:'equal',label:'Equal selected participants'},{value:'custom',label:'Custom percentages'},{value:'provisional',label:'Effective provisional ownership agreement'},{value:'formal',label:'Effective confirmed formal share register'}]},{key:'category_id',label:'Expense account category',type:'select',options:[{value:'',label:'Default policy'},...postingAccounts(accounts.data,'expense').map(a=>({value:String(a.id),label:`${a.code} · ${a.name}`}))]}]} extraDirty={Object.keys(weights).length>0} onClose={onClose} onSave={v=>api.post('/founders/policies/',{...body(v),effective_until:v.effective_until || null,weights})}>
    {v=><div className="mt-4 space-y-3"><Banner tone="info">Sharing is independent of ownership unless you explicitly select an ownership basis. Each approved expense preserves its effective policy and exact allocations.</Banner>{['equal','custom'].includes(String(v.basis)) && <WeightEditor parties={parties.data?.results.filter(p=>p.is_founder && p.is_active) ?? []} values={weights} onChange={setWeights} equal={v.basis==='equal'}/>}</div>}
  </FormDrawer>;
}

function SharingDrawer({onClose}:{onClose:()=>void}) {
  const parties=useParties(); const config=useConfig(); const payments=useApi<Page<CorporateTransaction>>('/founders/transactions/?status=posted&page_size=100');
  return <FormDrawer title="Allocate an approved shared cost" eyebrow="Personal sharing · no new expense posting" initial={{source:'expense',source_id:'',payer_id:'',date:today(),currency:config.data?.base_currency ?? '',amount:'',description:''}} fields={[{key:'source',label:'Cost source',type:'select',options:[{value:'expense',label:'Posted founder-paid company expense'},{value:'vendor_payment',label:'Posted vendor bill paid personally'},{value:'personal',label:'Personal-only shared cost (outside company books)'}]},{key:'source_id',label:'Posted founder payment',type:'select',options:[{value:'',label:'Select source when using company evidence…'},...(payments.data?.results ?? []).filter(t=>['expense','vendor_payment'].includes(t.kind)).map(t=>({value:String(t.id),label:`#${t.id} · ${t.kind} · ${t.party_name} · ${t.amount} ${t.currency}`}))]},{key:'payer_id',label:'Original payer (personal-only)',type:'select',options:partyOptions(parties.data?.results)},{key:'date',label:'Cost date (personal-only)',type:'date'},{key:'currency',label:'Currency',type:'select',options:(config.data?.enabled_currencies ?? []).map(value=>({value,label:value}))},{key:'amount',label:'Amount (personal-only)',type:'amount'},{key:'description',label:'Description (personal-only)'}]} onClose={onClose} onSave={v=>{
    if(v.source==='personal') return api.post('/founders/sharing/',{payer_id:Number(v.payer_id),date:v.date,currency:v.currency,amount:v.amount,description:v.description});
    const source=payments.data?.results.find(p=>p.id===Number(v.source_id)); if(!source) throw new Error('Select a posted cost source.');
    return api.post('/founders/sharing/',source.kind==='expense' ? {expense_id:source.expense} : {founder_payment_id:source.id});
  }}><Banner tone="warn">Approving sharing may create personal obligations. It never posts a second company expense or clears the company&apos;s existing founder liability.</Banner></FormDrawer>;
}

export function SharingPage() {
  const {can}=useAuth(); const money=useMoney(); const parties=useParties(); const params=useSearchParams(); const requestedTab=params.get('tab'); const [tab,setTab]=useState(requestedTab&&['policies','monthly','forecast','reserves','contributions','allocations'].includes(requestedTab)?requestedTab:'policies'); const [policy,setPolicy]=useState(false); const [allocate,setAllocate]=useState(false); const [error,setError]=useState<string|null>(null); const [busy,setBusy]=useState(false);
  const tabs=[{value:'policies',label:'Policies'},{value:'monthly',label:'Monthly Planner'},{value:'forecast',label:'12-month Forecast'},{value:'reserves',label:'Annual Reserves'},{value:'contributions',label:'Contribution Progress'},{value:'allocations',label:'Settlement Allocations'}];
  return <Screen eyebrow="Founder Finance" title="Expense sharing & funding" description="Actual shared costs, future funding targets and company money are tracked separately. Historical policies and forecasts stay frozen." actions={<div className="flex gap-2">{can('founder.settlements.manage') && can('founder.personal.view') && <Button onClick={()=>setAllocate(true)}>Allocate shared expense</Button>}{can('founder.planning.manage') && <Button variant="primary" onClick={()=>setPolicy(true)}>New sharing policy</Button>}</div>}>
    <div className="overflow-x-auto"><Segmented label="Expense sharing section" value={tab} onChange={setTab} options={tabs}/></div>
    {error && <Banner tone="err">{error}</Banner>}
    {tab==='policies' && <ListPanel<Policy> path="/founders/policies/" title="Sharing policies" columns={[{key:'name',label:'Policy',render:p=><Primary title={p.name} sub={p.basis}/>},{key:'date',label:'Effective dates',render:p=>`${p.effective_from} → ${p.effective_until || 'open ended'}`},{key:'weights',label:'Participants / basis',render:p=>Object.entries(p.weights).map(([id,value])=>`${parties.data?.results.find(p=>p.id===Number(id))?.name ?? id}: ${value}`).join(' · ') || `${p.basis} ownership on cost date`},{key:'status',label:'Status',render:p=><StatusBadge status={p.status}/>},{key:'activate',label:'',render:p=>can('founder.planning.manage') && p.status==='draft' && <Button size="xs" disabled={busy} onClick={async()=>{setBusy(true);setError(null);try{await act(()=>api.post(`/founders/policies/${p.id}/activate/`,{}),'Policy activation processed');}catch(e){setError(errorMessage(e));}finally{setBusy(false);}}}>Activate / submit</Button>}]}/>}
    {['monthly','forecast'].includes(tab) && <Gate allow={can('founder.planning.manage')} what="funding planning"><PlannerPageContent months={tab==='monthly' ? 1 : 12}/></Gate>}
    {tab==='reserves' && <Gate allow={can('founder.planning.manage')} what="annual reserves"><ReserveContent/></Gate>}{tab==='contributions' && <Gate allow={can('founder.planning.manage')} what="funding progress"><ContributionContent/></Gate>}
    {tab==='allocations' && (can('founder.personal.view') ? <ListPanel<SharedExpense> path="/founders/sharing/" title="Frozen approved expense allocations" columns={[{key:'source',label:'Cost',render:s=><Primary title={s.description} sub={`${s.date} · ${s.snapshot.personal_only ? 'Personal-only, no GL' : 'Linked company cost'}`}/>},{key:'policy',label:'Policy',render:s=>s.snapshot.policy},{key:'shares',label:'Participant shares',render:s=>Object.entries(s.snapshot.amounts).map(([id,amount])=><div key={id}>{parties.data?.results.find(p=>p.id===Number(id))?.name ?? id}: {money(amount,s.currency)}</div>)},{key:'amount',label:'Total',align:'right',render:s=>money(s.amount,s.currency)}]}/> : <Banner tone="info">Personal sharing access is required for settlement allocations.</Banner>)}
    {policy && <PolicyDrawer onClose={()=>setPolicy(false)}/>}{allocate && <SharingDrawer onClose={()=>setAllocate(false)}/>}
  </Screen>;
}
