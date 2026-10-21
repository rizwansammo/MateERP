'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Choice';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { InfoPanel } from '@/components/ui/InfoPanel';
import { Input, Select } from '@/components/ui/Input';
import { Spinner } from '@/components/ui/Spinner';
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/Table';
import { useAccounts, JournalLink } from '@/features/accounting/shared';
import { decimal, minor } from '@/features/accounting/money';
import type { Year } from '@/features/accounting/types';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { Card, Gate, ListPanel, Primary, StatusBadge, act, useApi, useMoney } from '@/features/commerce/shared';
import type { Project } from '@/features/commerce/types';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { CostClassification, type SpendingLine } from './CostClassification';

interface Center {id:number;code:string;name:string;description:string;department:string;owner_reference:string;categories:string[];is_active:boolean}
interface Budget {id:number;name:string;fiscal_year_id:number;fiscal_start:string;fiscal_end:string;owner_reference:string;is_archived:boolean;active_revision_id:number|null;original_revision_id:number|null}
interface BudgetLine {id:number;month:string;account_id:number;account_code:string;category:string;cost_center_id:number|null;project_id:number|null;amount:string}
interface Revision {id:number;budget_id:number;version:number;notes:string;status:string;approval_id:number|null;lines:BudgetLine[]}
interface Comparison {id:number;month:string;account_code:string;account_name:string;category:string;cost_center:string|null;original:string;revised:string;actual:string;remaining:string;variance:string;over_budget:boolean}
interface EditLine {month:string;account_id:string;category:string;cost_center_id:string;project_id:string;amount:string;annual:boolean}
const categories=[{value:'operating',label:'Operating expense'},{value:'cogs',label:'Cost of sales'},{value:'capex',label:'Fixed-asset additions'},{value:'tax',label:'Recoverable tax'}];

/** A display ratio of authoritative GL/plan values; never convert amounts to Number. */
function utilization(actual:string, planned:string) {
  const budget=minor(planned);if(budget<=0n)return '—';
  const value=minor(actual);const magnitude=value<0n?-value:value;
  const tenths=(magnitude*1000n+budget/2n)/budget;
  return `${decimal(value<0n?-tenths:tenths,1).replace(/\.0$/,'')}%`;
}

function CenterDrawer({center,onClose}:{center?:Center;onClose:()=>void}) {
  return <FormDrawer title={center?'Edit cost center':'New cost center'} eyebrow="Budgets & Costs" onClose={onClose}
    initial={{code:center?.code??'',name:center?.name??'',description:center?.description??'',department:center?.department??'',owner_reference:center?.owner_reference??'',is_active:center?.is_active??true}}
    fields={[{key:'code',label:'Code',required:true},{key:'name',label:'Name',required:true},{key:'department',label:'Department / function'},
      {key:'owner_reference',label:'Owner / contact reference'},{key:'description',label:'Description',type:'textarea'},{key:'is_active',label:'Active',type:'checkbox'}]}
    description="An internal management dimension. Deactivation retains all historical classifications and budgets."
    onSave={v=>center?api.patch(`/budgeting/cost-centers/${center.id}/`,v):api.post('/budgeting/cost-centers/',{...v,categories:[]})} />;
}

function BudgetDrawer({onClose}:{onClose:()=>void}) {
  const years=useApi<Page<Year>>('/accounting/fiscal-years/?page_size=100');
  return <FormDrawer title="New budget" eyebrow="Budgets & Costs" onClose={onClose} initial={{name:'',fiscal_year_id:'',owner_reference:''}}
    fields={[{key:'name',label:'Budget name',required:true},{key:'fiscal_year_id',label:'Fiscal year',type:'select',options:[{value:'',label:'Choose fiscal year'},...(years.data?.results??[]).map(y=>({value:String(y.id),label:`${y.name} · ${y.start} — ${y.end}`}))]},
      {key:'owner_reference',label:'Budget owner / contact reference'}]} onSave={v=>api.post('/budgeting/budgets/',body(v))} />;
}

function RevisionDrawer({budget,latest,onClose}:{budget:Budget;latest?:Revision;onClose:()=>void}) {
  const accounts=useAccounts();const centers=useApi<Page<Center>>('/budgeting/cost-centers/?page_size=100');const projects=useApi<Page<Project>>('/sales/projects/?page_size=100');
  const blank=():EditLine=>({month:budget.fiscal_start.slice(0,7),account_id:'',category:'operating',cost_center_id:'',project_id:'',amount:'',annual:false});
  const [lines,setLines]=useState<EditLine[]>(latest?latest.lines.map(l=>({month:l.month.slice(0,7),account_id:String(l.account_id),category:l.category,cost_center_id:l.cost_center_id?String(l.cost_center_id):'',project_id:l.project_id?String(l.project_id):'',amount:l.amount,annual:false})):[blank()]);
  const [initial]=useState(JSON.stringify(lines));
  const set=(i:number,patch:Partial<EditLine>)=>setLines(ls=>ls.map((l,n)=>n===i?{...l,...patch}:l));
  return <FormDrawer title="New budget revision" eyebrow={budget.name} width={1160} onClose={onClose} initial={{notes:''}}
    description="Each revision is retained. Annual amounts are allocated across fiscal months by the server using exact minor units. Independent approval activates coverage; overlapping scopes are rejected."
    extraDirty={initial!==JSON.stringify(lines)} fields={[{key:'notes',label:'Revision purpose and authority',type:'textarea',required:true}]}
    onSave={v=>api.post(`/budgeting/budgets/${budget.id}/revise/`,{notes:v.notes,lines:lines.map(l=>({month:`${l.month}-01`,account_id:Number(l.account_id),category:l.category,cost_center_id:l.cost_center_id?Number(l.cost_center_id):null,project_id:l.project_id?Number(l.project_id):null,amount:l.amount,annual:l.annual}))})}>
    <div className="overflow-x-auto"><Table><THead><TR><TH>Month / year</TH><TH>Category</TH><TH>Account</TH><TH>Cost center</TH><TH>Project</TH><TH>Base amount</TH><TH /></TR></THead><TBody>{lines.map((l,i)=><TR key={i}>
      <TD><Input aria-label={`Line ${i+1} month`} type="month" value={l.month} onChange={e=>set(i,{month:e.target.value})} /><Checkbox label="Annual total" checked={l.annual} onChange={v=>set(i,{annual:v})} /></TD>
      <TD><Select aria-label={`Line ${i+1} category`} value={l.category} onChange={e=>set(i,{category:e.target.value,account_id:''})}>{categories.map(c=><option key={c.value} value={c.value}>{c.label}</option>)}</Select></TD>
      <TD><Select aria-label={`Line ${i+1} account`} value={l.account_id} onChange={e=>set(i,{account_id:e.target.value})}><option value="">Choose account</option>{accounts.data?.filter(a=>a.is_postable&&a.is_active&&(l.category==='capex'?a.control==='fixed_assets':l.category==='tax'?a.account_type==='asset':a.account_type==='expense'&&!a.control)).map(a=><option key={a.id} value={a.id}>{a.code} · {a.name}</option>)}</Select></TD>
      <TD><Select aria-label={`Line ${i+1} cost center`} value={l.cost_center_id} onChange={e=>set(i,{cost_center_id:e.target.value})}><option value="">All cost centers</option>{centers.data?.results.filter(c=>c.is_active).map(c=><option key={c.id} value={c.id}>{c.code}</option>)}</Select></TD>
      <TD><Select aria-label={`Line ${i+1} project`} value={l.project_id} onChange={e=>set(i,{project_id:e.target.value})}><option value="">All projects</option>{projects.data?.results.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</Select></TD>
      <TD><Input aria-label={`Line ${i+1} budget amount`} inputMode="decimal" value={l.amount} onChange={e=>set(i,{amount:e.target.value})} /></TD>
      <TD><Button aria-label={`Remove budget line ${i+1}`} size="xs" disabled={lines.length===1} onClick={()=>setLines(ls=>ls.filter((_,n)=>n!==i))}>Remove</Button></TD>
    </TR>)}</TBody></Table></div><Button size="sm" onClick={()=>setLines(ls=>[...ls,blank()])}>Add budget line</Button>
  </FormDrawer>;
}

function ComparisonPanel({revision}:{revision:Revision}) {
  const data=useApi<Comparison[]>(revision.status==='approved'?`/budgeting/revisions/${revision.id}/comparison/`:null);const money=useMoney();const {can}=useAuth();const [drill,setDrill]=useState<number|null>(null);
  if(revision.status!=='approved')return <Banner tone="info">Draft and pending revisions are proposed plans. Approve this revision to compare authorized coverage against posted GL spending.</Banner>;
  return <>{Boolean(data.error)&&<Banner tone="err">{errorMessage(data.error)}</Banner>}
    <Card title={`Original vs revised vs posted actual — v${revision.version}`}><div className="overflow-x-auto"><Table><THead><TR><TH>Month / scope</TH><TH>Category</TH><TH align="right">Original</TH><TH align="right">Revised</TH><TH align="right">Actual</TH><TH align="right">Utilized</TH><TH align="right">Remaining</TH><TH align="right">Variance</TH><TH /></TR></THead><TBody>{data.data?.map(r=><TR key={r.id}>
      <TD><Primary title={`${r.month.slice(0,7)} · ${r.account_code}`} sub={`${r.account_name} · ${r.cost_center??'All cost centers'}`} /></TD><TD>{r.category}</TD><TD align="right">{money(r.original)}</TD><TD align="right">{money(r.revised)}</TD><TD align="right">{money(r.actual)}</TD><TD align="right">{utilization(r.actual,r.revised)}</TD><TD align="right">{money(r.remaining)}</TD><TD align="right"><span className={r.over_budget?'text-err':'text-tx'}>{money(r.variance)}</span></TD><TD><Button size="xs" onClick={()=>setDrill(r.id)}>Source details</Button></TD>
    </TR>)}</TBody></Table></div></Card>
    <Banner tone="info">Actuals use posted base-currency GL amounts and audited analytical classifications. Drafts, forecasts and unpaid approval requests are excluded. CAPEX shows fixed-asset additions; recoverable taxes are separate. Warnings do not block payment. {can('founder.view')&&can('founder.planning.manage')?<Link href="/founder/sharing?tab=monthly">Funding forecasts remain separate</Link>:'Funding forecasts remain separate'}.</Banner>
    {drill!==null&&<ListPanel<SpendingLine> key={drill} title="Underlying posted sources" path={`/budgeting/revisions/${revision.id}/actuals/?line_id=${drill}`} columns={[
      {key:'journal',label:'Source journal',render:l=><JournalLink id={l.journal_id}>{l.number}</JournalLink>},{key:'date',label:'Posted date',render:l=>formatDate(l.date)},
      {key:'description',label:'Description',render:l=>l.description},{key:'debit',label:'Debit',align:'right',render:l=>money(l.base_debit)},{key:'credit',label:'Credit',align:'right',render:l=>money(l.base_credit)},
    ]} />}
  </>;
}

function BudgetDetail({id}:{id:string}) {
  const budget=useApi<Budget>(`/budgeting/budgets/${id}/`);const revisions=useApi<Page<Revision>>(`/budgeting/revisions/?budget_id=${id}&page_size=100`);
  const {can}=useAuth();const [create,setCreate]=useState(false);const [selected,setSelected]=useState('');const [submit,setSubmit]=useState<Revision|null>(null);
  const b=budget.data;const latest=revisions.data?.results[0];const chosen=revisions.data?.results.find(r=>String(r.id)===(selected||String(b?.active_revision_id??latest?.id)));
  if(!b)return <Screen title="Budget" eyebrow="Budgets & Costs">{budget.error?<Banner tone="err">{errorMessage(budget.error)}</Banner>:<Spinner />}</Screen>;
  return <Screen title={b.name} eyebrow="Budgets & Costs" description={`${b.fiscal_start} — ${b.fiscal_end} · Company base currency`}
    actions={can('budgets.manage')&&!b.is_archived&&<Button variant="primary" onClick={()=>setCreate(true)}>New revision</Button>}>
    <InfoPanel title="Approved coverage" rows={[{label:'Status',value:b.is_archived?'Archived':'Active'},{label:'Owner reference',value:b.owner_reference||'—'},{label:'Original approved version',value:b.original_revision_id?`Revision #${b.original_revision_id}`:'Not approved'},{label:'Current approved version',value:b.active_revision_id?`Revision #${b.active_revision_id}`:'Not approved'}]} />
    {Boolean(revisions.error)&&<Banner tone="err">{errorMessage(revisions.error)}</Banner>}
    <Select aria-label="Budget revision" value={chosen?String(chosen.id):''} onChange={e=>setSelected(e.target.value)}><option value="">Choose revision</option>{revisions.data?.results.map(r=><option key={r.id} value={r.id}>v{r.version} · {r.status}</option>)}</Select>
    {chosen&&<><InfoPanel title={`Revision v${chosen.version}`} rows={[{label:'Status',value:<StatusBadge status={chosen.status} />},{label:'Purpose',value:chosen.notes},{label:'Approval',value:chosen.approval_id?<Link href="/settings/approvals">Review retained request</Link>:'Not submitted'}]} />
      {chosen.status==='draft'&&can('budgets.manage')&&<Button variant="primary" onClick={()=>setSubmit(chosen)}>Submit revision for approval</Button>}
      <ComparisonPanel key={chosen.id} revision={chosen} />
      {chosen.status!=='approved'&&<Card title="Proposed monthly allocations"><Table><THead><TR><TH>Month</TH><TH>Account</TH><TH>Category</TH><TH>Base amount</TH></TR></THead><TBody>{chosen.lines.map(l=><TR key={l.id}><TD>{l.month.slice(0,7)}</TD><TD>{l.account_code}</TD><TD>{l.category}</TD><TD>{l.amount}</TD></TR>)}</TBody></Table></Card>}
    </>}
    {create&&<RevisionDrawer budget={b} latest={latest} onClose={()=>setCreate(false)} />}
    <ConfirmDialog open={submit!==null} title={`Submit v${submit?.version??''} for independent review?`} confirmLabel="Submit for approval" onCancel={()=>setSubmit(null)} onConfirm={async()=>{await act(()=>api.post(`/budgeting/revisions/${submit!.id}/submit/`),'Budget revision submitted; active coverage is unchanged until approval');setSubmit(null);}} />
  </Screen>;
}

export function BudgetsApp({section,id}:{section:string;id?:string}) {
  const {can}=useAuth();const [center,setCenter]=useState<Center|'new'|null>(null);const [create,setCreate]=useState(false);const [archived,setArchived]=useState<Budget|null>(null);
  return <Gate allow={can('finance.view')}>{id?<BudgetDetail id={id} />:<Screen title={section==='costcenters'?'Cost Centers':section==='comparison'?'Budget Comparisons':'Budgets'} eyebrow="Budgets & Costs"
    description="Approved spending plans and posted actuals, with separate operating, cost-of-sales, capital and tax scopes."
    actions={can('budgets.manage')&&<Button variant="primary" onClick={()=>section==='costcenters'?setCenter('new'):setCreate(true)}>{section==='costcenters'?'New cost center':'New budget'}</Button>}>
    {section==='costcenters'?<><ListPanel<Center> path="/budgeting/cost-centers/" columns={[
      {key:'code',label:'Code',render:c=><Primary mono title={c.code} sub={c.name} />},{key:'dept',label:'Department',render:c=>c.department||'—'},{key:'owner',label:'Owner reference',render:c=>c.owner_reference||'—'},
      {key:'active',label:'Status',render:c=>c.is_active?'Active':'Inactive'},{key:'edit',label:'Actions',render:c=>can('budgets.manage')&&<Button size="xs" onClick={()=>setCenter(c)}>Edit</Button>},
    ]} /><CostClassification /></>:<ListPanel<Budget> path="/budgeting/budgets/" filters={[{value:'all',label:'All'},{value:'active',label:'Active',query:'status=active'},{value:'archived',label:'Archived',query:'status=archived'}]} columns={[
      {key:'name',label:'Budget',render:b=><Primary title={b.name} href={`/budgets/budgets/${b.id}`} sub={b.owner_reference} />},{key:'year',label:'Fiscal year',render:b=>`${b.fiscal_start} — ${b.fiscal_end}`},
      {key:'active',label:'Coverage',render:b=>b.is_archived?'Archived':b.active_revision_id?'Approved revision active':'No approved revision'},
      {key:'act',label:'Actions',render:b=>can('budgets.manage')&&can('budgets.approve')&&<Button size="xs" onClick={()=>setArchived(b)}>{b.is_archived?'Restore':'Archive'}</Button>},
    ]} />}
    {center&&<CenterDrawer center={center==='new'?undefined:center} onClose={()=>setCenter(null)} />}{create&&<BudgetDrawer onClose={()=>setCreate(false)} />}
    <ConfirmDialog open={archived!==null} title={`${archived?.is_archived?'Restore':'Archive'} budget?`} confirmLabel={archived?.is_archived?'Restore':'Archive'} onCancel={()=>setArchived(null)} onConfirm={async()=>{await act(()=>api.patch(`/budgeting/budgets/${archived!.id}/`,{is_archived:!archived!.is_archived}),'Budget availability updated; approved history retained');setArchived(null);}} />
  </Screen>}</Gate>;
}
