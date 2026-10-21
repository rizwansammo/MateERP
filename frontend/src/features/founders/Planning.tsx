'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Banner } from '@/components/ui/Banner';
import { Field } from '@/components/ui/Field';
import { Checkbox } from '@/components/ui/Choice';
import type { Bill, Expense, ExpenseSchedule } from '@/features/commerce/types';
import { Input, Select } from '@/components/ui/Input';
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table';
import { FormDrawer, body } from '@/features/commerce/forms';
import { Card, ListPanel, Primary, StatusBadge, positive, useApi, useMoney, today } from '@/features/commerce/shared';
import { useConfig } from '@/features/accounting/shared';
import type { Bank } from '@/features/accounting/types';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import type { Forecast, ForecastRow, FundingProgressRow, FundingPlan, Reserve, CorporateTransaction, Pledge, Designation, CompanyCoverage } from './types';
import { partyOptions, useParties } from './shared';

function ForecastTable({ rows }: { rows: ForecastRow[] }) {
  const money = useMoney();
  const parties = useParties();
  return <Card title="Funding forecast" subtitle="Expected costs, reserve installments and verified funding remain distinct.">
    <Table><THead><TR><TH>Month</TH><TH>Currency</TH><TH align="right">Expected cost</TH><TH align="right">Reserve installment</TH><TH align="right">Verified renewal cover</TH><TH align="right">Funding target</TH><TH>Founder targets</TH><TH>FX estimate</TH></TR></THead>
      <TBody>{rows.map(r => <TR key={`${r.month}:${r.currency}`}>
        <TD>{r.month.slice(0, 7)}</TD><TD>{r.currency}</TD><TD align="right">{money(r.cost, r.currency)}</TD>
        <TD align="right">{money(r.reserve_target, r.currency)}</TD><TD align="right">{money(r.reserve_coverage, r.currency)}</TD><TD align="right">{money(r.founder_request, r.currency)}</TD>
        <TD>{Object.entries(r.founders).map(([id, amount]) => <div key={id}>{parties.data?.results.find(p => p.id === Number(id))?.name ?? id}: {money(amount, r.currency)}</div>)}</TD>
        <TD>{r.estimated_base_cost === null ? 'Missing rate' : `${r.estimated_rate} · ${r.rate_source}`}</TD>
      </TR>)}{!rows.length && <TR><TD colSpan={8}>No configured costs fall within this period.</TD></TR>}</TBody>
    </Table>
  </Card>;
}

export function PlannerPageContent({ months }: { months: number }) {
  const [sourcesOpen,setSourcesOpen]=useState(false);
  const [allSchedules,setAllSchedules]=useState(true);
  const [scheduleIds,setScheduleIds]=useState<number[]>([]);
  const [expenseIds,setExpenseIds]=useState<number[]>([]);
  const [billIds,setBillIds]=useState<number[]>([]);
  const schedules=useApi<Page<ExpenseSchedule>>(sourcesOpen ? '/purchasing/recurring/?page_size=100' : null);
  const expenses=useApi<Page<Expense>>(sourcesOpen ? '/purchasing/expenses/?page_size=100' : null);
  const bills=useApi<Page<Bill>>(sourcesOpen ? '/purchasing/bills/?page_size=100' : null);
  const [starts, setStarts] = useState(`${today().slice(0, 7)}-01`);
  const [mode, setMode] = useState('founders');
  const [name, setName] = useState('');
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [selected, setSelected] = useState<FundingPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (save: boolean) => {
    if (busy) return;
    setBusy(true); setError(null);
    try {
      const data = { starts, months, mode, name: name || `Funding forecast ${starts.slice(0, 7)}`, ...(allSchedules ? {} : {schedule_ids:scheduleIds}),expense_ids:expenseIds,bill_ids:billIds,...(selected ? {previous_id:selected.id} : {}) };
      if (save) {
        const plan = await api.post<FundingPlan>('/founders/plans/', data);
        setSelected(plan); setForecast(plan.snapshot);
      } else {
        setForecast(await api.post<Forecast>('/founders/plans/preview/', data)); setSelected(null);
      }
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };
  return <>
    <Banner tone="info">Forecasts use actual recurring-expense schedules. Generated drafts replace the same occurrence. Promises and reserve targets never become company cash.</Banner>
    <Card title={months === 1 ? 'Monthly funding planner' : 'Rolling 12-month forecast'}>
      <div className="grid gap-3 p-4 sm:grid-cols-3">
        <Field label="Starts" htmlFor="plan-start"><Input id="plan-start" type="date" value={starts} onChange={e => { setStarts(e.target.value); setForecast(null); }} /></Field>
        <Field label="Funding mode" htmlFor="plan-mode"><Select id="plan-mode" value={mode} onChange={e => { setMode(e.target.value); setForecast(null); }}><option value="founders">Founder-funded</option><option value="partial">Partially company-funded</option><option value="self_sustaining">Self-sustaining · no founder request</option></Select></Field>
        <Field label="Snapshot name" htmlFor="plan-name"><Input id="plan-name" value={name} onChange={e => setName(e.target.value)} /></Field>
        <div className="flex flex-wrap gap-2 sm:col-span-3"><Button onClick={()=>setSourcesOpen(!sourcesOpen)}>Choose cost sources</Button><Button disabled={busy} onClick={() => void run(false)}>Preview forecast</Button><Button variant="primary" disabled={busy} onClick={() => void run(true)}>Save immutable forecast</Button></div>
      </div>
    </Card>
    {sourcesOpen && <Card title="Forecast sources" subtitle="Recurring occurrences are deduplicated against actual expenses. Select one-off costs explicitly."><div className="grid gap-4 p-4 lg:grid-cols-3"><div><Checkbox label="Include all recurring schedules" checked={allSchedules} onChange={checked=>{setAllSchedules(checked);setForecast(null);}}/>{!allSchedules && schedules.data?.results.map(s=><Checkbox key={s.id} label={s.name} checked={scheduleIds.includes(s.id)} onChange={checked=>{setScheduleIds(checked ? [...scheduleIds,s.id] : scheduleIds.filter(id=>id!==s.id));setForecast(null);}}/>)}</div><div><h3 className="mb-2 font-semibold">One-off expenses</h3>{expenses.data?.results.filter(e=>!e.recurring_schedule_id).map(e=><Checkbox key={e.id} label={`${e.description} · ${e.total} ${e.currency}`} checked={expenseIds.includes(e.id)} onChange={checked=>{setExpenseIds(checked ? [...expenseIds,e.id] : expenseIds.filter(id=>id!==e.id));setForecast(null);}}/>)}</div><div><h3 className="mb-2 font-semibold">Vendor obligations</h3>{bills.data?.results.map(b=><Checkbox key={b.id} label={`${b.vendor_reference} · ${b.total} ${b.currency}`} checked={billIds.includes(b.id)} onChange={checked=>{setBillIds(checked ? [...billIds,b.id] : billIds.filter(id=>id!==b.id));setForecast(null);}}/>)}</div>{Boolean(schedules.error || expenses.error || bills.error) && <Banner tone="err">{errorMessage(schedules.error || expenses.error || bills.error)}</Banner>}</div></Card>}
    {error && <Banner tone="err">{error}</Banner>}
    {forecast?.issues.map((issue, index) => <Banner key={index} tone="warn">{issue.source}: {issue.message}</Banner>)}
    {forecast && <ForecastTable rows={forecast.rows} />}
    {selected && <Banner tone="ok">Saved forecast #{selected.id}. Future refreshes create another revision.</Banner>}
    <ListPanel<FundingPlan> path="/founders/plans/" title="Saved forecast history" columns={[
      { key: 'name', label: 'Forecast', render: p => <Primary title={p.name} sub={`${p.starts} · ${p.months} months`} /> },
      { key: 'mode', label: 'Mode', render: p => p.mode },
      { key: 'view', label: '', render: p => <Button size="xs" onClick={() => { setSelected(p); setForecast(p.snapshot); }}>View snapshot</Button> },
    ]} />
  </>;
}

export function ReserveContent() {
  const money = useMoney();
  const [create, setCreate] = useState(false);
  const [revision, setRevision] = useState<Reserve | null>(null);
  const schedules = useApi<Page<{ id: number; name: string; currency: string }>>('/purchasing/recurring/?page_size=100');
  return <>
    <Banner tone="info">Planned reserves are not expenses or cash. Only verified designated receipts count as funded. The renewal month collects the remaining requirement once.</Banner>
    <ListPanel<Reserve> path="/founders/reserves/" title="Annual reserve cycles" actions={<Button size="sm" onClick={() => setCreate(true)}>Plan annual reserve</Button>} columns={[
      { key: 'name', label: 'Reserve', render: r => <Primary title={r.name} sub={`${r.starts} → ${r.renewal}`} /> },
      { key: 'target', label: 'Target', align: 'right', render: r => money(r.target, r.currency) },
      { key: 'actual', label: 'Usable verified funding', align: 'right', render: r => money(r.progress.usable, r.currency) },
      { key: 'spent', label: 'Consumed once', align: 'right', render: r => money(r.progress.consumed, r.currency) },
      {key:'released',label:'Released / rolled forward',align:'right',render:r=>money(r.progress.released ?? '0',r.currency)},
      { key: 'gap', label: 'Shortfall', align: 'right', render: r => money(r.progress.shortfall, r.currency) },
      { key: 'status', label: 'Status', render: r => <StatusBadge status={r.status} /> },
      { key: 'revise', label: '', render: r => r.status === 'active' && <Button size="xs" onClick={() => setRevision(r)}>Revise / reschedule</Button> },
    ]} />
    {create && <FormDrawer title="Plan annual renewal reserve" eyebrow="No accounting entry" onClose={() => setCreate(false)} initial={{ name: '', schedule_id: '', starts: `${today().slice(0, 4)}-01-01`, renewal: '', target: '' }} fields={[
      { key: 'name', label: 'Reserve name', required: true },
      { key: 'schedule_id', label: 'Existing recurring expense', type: 'select', options: [{ value: '', label: 'Select renewal schedule…' }, ...(schedules.data?.results ?? []).map(s => ({ value: String(s.id), label: `${s.name} · ${s.currency}` }))] },
      { key: 'starts', label: 'Start collecting from', type: 'date' }, { key: 'renewal', label: 'Actual scheduled renewal', type: 'date' },
      { key: 'target', label: 'Renewal target in schedule currency', type: 'amount' },
    ]} onSave={v => api.post('/founders/reserves/', body(v))} />}
    {revision && <FormDrawer title="Revise reserve and retain funding history" eyebrow="Explicit reserve rollover" onClose={() => setRevision(null)} initial={{name:revision.name,schedule_id:String(revision.schedule),starts:revision.starts,renewal:revision.renewal,target:revision.target,reason:''}} fields={[
      {key:'name',label:'Revised reserve name',required:true},{key:'starts',label:'Revised collection start',type:'date'},{key:'renewal',label:'Actual scheduled renewal date',type:'date'},{key:'target',label:'Revised target',type:'amount'},{key:'reason',label:'Reason and authority to carry retained funding',type:'textarea',required:true},
    ]} onSave={v=>api.post('/founders/reserves/',{...body(v),previous_id:revision.id})}><Banner tone="warn">Unused funding is released and designated into the new cycle with an immutable transfer record. Prior payments remain in the original cycle. For a consumed cycle, select a later actual renewal and its new collection start.</Banner></FormDrawer>}
  </>;
}

export function ContributionContent() {
  const [releaseFunding,setReleaseFunding]=useState<{value:Designation;key:string}|null>(null);
  const [updatePledge,setUpdatePledge]=useState<Pledge|null>(null);
  const parties = useParties(); const config = useConfig(); const money = useMoney();
  const plans = useApi<Page<FundingPlan>>('/founders/plans/?page_size=100');
  const reserves = useApi<Page<Reserve>>('/founders/reserves/?page_size=100');
  const receipts = useApi<Page<CorporateTransaction>>('/founders/transactions/?kind=receipt&status=posted&page_size=100');
  const [pledge, setPledge] = useState(false); const [designation, setDesignation] = useState(false);
  const [consume, setConsume] = useState<Designation | null>(null); const [plan, setPlan] = useState('');
  const banks = useApi<Page<Bank>>('/banking/accounts/?page_size=100');
  const [company, setCompany] = useState(false);
  const [coverage, setCoverage] = useState<CompanyCoverage|null>(null);
  const [releaseConsumption, setReleaseConsumption] = useState<number|null>(null);
  const progress = useApi<FundingProgressRow[]>(plan ? `/founders/plans/${plan}/progress/` : null);
  return <>
    <Banner tone="info">Requests and promises are not receipts. First independently verify actual company funding, then designate available funds once.</Banner>
    <Card title="Contribution progress" actions={<div className="flex flex-wrap gap-2"><Button size="sm" onClick={() => setPledge(true)}>Record request / promise</Button><Button size="sm" onClick={() => setDesignation(true)}>Designate verified receipt</Button><Button size="sm" onClick={()=>setCompany(true)}>Allocate existing company cash</Button></div>}>
      <div className="p-4"><Field label="Saved plan" htmlFor="funding-progress"><Select id="funding-progress" value={plan} onChange={e => setPlan(e.target.value)}><option value="">Choose forecast…</option>{plans.data?.results.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field></div>
      {Boolean(progress.error) && <Banner tone="err">{errorMessage(progress.error)}</Banner>}
      {progress.data && <Table><THead><TR><TH>Month</TH><TH align="right">Target</TH><TH align="right">Company coverage</TH><TH align="right">Verified designated</TH><TH align="right">Remaining request</TH><TH>Founder progress</TH></TR></THead><TBody>{progress.data.map(r => <TR key={`${r.month}:${r.currency}`}><TD>{r.month.slice(0, 7)} · {r.currency}</TD><TD align="right">{money(r.founder_request, r.currency)}</TD><TD align="right">{money(r.company_coverage,r.currency)}</TD><TD align="right">{money(r.verified_designated, r.currency)}</TD><TD align="right">{money(r.remaining, r.currency)}</TD><TD>{Object.entries(r.remaining_founder_targets ?? {}).map(([id,target])=><div key={id}>{parties.data?.results.find(p=>p.id===Number(id))?.name ?? id}: {money(r.verified_by_founder?.[id],r.currency)} verified / {money(target,r.currency)} target · {money(r.remaining_by_founder?.[id],r.currency)} due · {money(r.surplus_by_founder?.[id],r.currency)} surplus</div>)}</TD></TR>)}</TBody></Table>}
    </Card>
    {progress.data && <Card title="Posted costs against saved estimates" subtitle="Only fulfilled forecast sources are compared. Actual historical rates stay separate from the saved estimate; price changes can also affect the variance.">
      <Table><THead><TR><TH>Month / source</TH><TH align="right">Saved base estimate</TH><TH align="right">Posted base cost</TH><TH>Actual rate</TH><TH align="right">Cost / FX variance</TH></TR></THead><TBody>
        {progress.data.flatMap(r=>(r.posted_costs ?? []).map(c=><TR key={`${r.month}:${c.identity}`}><TD><Primary href={`/banking/journals/${c.journal_id}`} title={c.name} sub={r.month.slice(0,7)}/></TD><TD align="right">{c.estimated_base_cost===null ? 'Missing saved rate' : money(c.estimated_base_cost,r.base_currency)}</TD><TD align="right">{money(c.actual_base_cost,r.base_currency)}</TD><TD>{c.actual_rate}</TD><TD align="right">{c.base_cost_variance===null ? 'Unavailable' : money(c.base_cost_variance,r.base_currency)}</TD></TR>))}
        {!progress.data.some(r=>r.posted_costs?.length) && <TR><TD colSpan={5}>No forecast sources have posted costs yet.</TD></TR>}
      </TBody></Table>
    </Card>}
    <ListPanel<Pledge> path="/founders/pledges/" title="Requests and promises · no company posting" columns={[
      { key: 'party', label: 'Participant', render: p => parties.data?.results.find(f => f.id === p.party)?.name ?? p.party },
      { key: 'month', label: 'Month', render: p => p.month }, { key: 'status', label: 'Status', render: p => p.status },
      { key: 'amount', label: 'Promised / requested', align: 'right', render: p => money(p.amount, p.currency) },
      {key:'update',label:'',render:p=>p.status!=='cancelled' && <Button size="xs" onClick={()=>setUpdatePledge(p)}>Update request</Button>},
    ]} />
    {updatePledge && <FormDrawer title="Update funding request" eyebrow="Planning only · no financial posting" onClose={()=>setUpdatePledge(null)} initial={{status:updatePledge.status==='requested' ? 'promised' : 'cancelled',reason:''}} fields={[{key:'status',label:'New planning status',type:'select',options:[...(updatePledge.status==='requested' ? [{value:'promised',label:'Promise confirmed'}] : []),{value:'cancelled',label:'Cancel request / promise'}]},{key:'reason',label:'Reason / confirmation reference',type:'textarea',required:true}]} onSave={v=>api.post(`/founders/pledges/${updatePledge.id}/status/`,v)}/>}
    <ListPanel<Designation> path="/founders/designations/" title="Verified funding allocations" columns={[
      { key: 'receipt', label: 'Company receipt', render: d => `#${d.receipt}` },
      { key: 'target', label: 'Allocated to', render: d => d.reserve ? `Reserve #${d.reserve}` : `Plan #${d.plan}` },
      { key: 'month', label: 'Month', render: d => d.month }, { key: 'amount', label: 'Amount', align: 'right', render: d => d.amount },
      { key: 'used', label: 'Consumption', render: d => <div className="space-y-2"><div>{d.remaining} retained</div>{d.consumptions.map(c=><div key={c.id}>Expense #{c.expense_id} · {c.amount} <Button size="xs" onClick={()=>setReleaseConsumption(c.id)}>Release allocation</Button></div>)}{positive(d.remaining) && <div className="flex flex-wrap gap-2"><Button size="xs" onClick={() => setConsume(d)}>Link actual paid expense</Button><Button size="xs" onClick={()=>setReleaseFunding({value:d,key:crypto.randomUUID()})}>Release unused funding</Button></div>}</div> },
    ]} />
    <ListPanel<CompanyCoverage> path="/founders/company-coverage/" title="Explicit company funding coverage" columns={[
      {key:'plan',label:'Plan',render:c=>`#${c.plan}`},{key:'month',label:'Month',render:c=>c.month},{key:'amount',label:'Company cash allocated',align:'right',render:c=>money(c.amount,c.currency)},{key:'reference',label:'Authority / reference',render:c=>c.reference},{key:'status',label:'Status',render:c=>c.status},{key:'resolve',label:'',render:c=>c.status!=='released' && <Button size="xs" onClick={()=>setCoverage(c)}>Consume / release</Button>},
    ]}/>
    {company && <FormDrawer title="Allocate existing company cash" eyebrow="Partial company funding · no cash posting" onClose={()=>setCompany(false)} initial={{plan_id:plan,bank_id:'',month:`${today().slice(0,7)}-01`,amount:'',reference:''}} fields={[
      {key:'plan_id',label:'Partial-funding forecast',type:'select',options:[{value:'',label:'Select partial plan…'},...(plans.data?.results ?? []).filter(p=>p.mode==='partial').map(p=>({value:String(p.id),label:p.name}))]},
      {key:'bank_id',label:'Company account with available posted funds',type:'select',options:[{value:'',label:'Select account…'},...(banks.data?.results ?? []).map(b=>({value:String(b.id),label:`${b.name} · ${b.currency}`}))]},
      {key:'month',label:'Funding month',type:'date'},{key:'amount',label:'Explicit company coverage amount',type:'amount'},{key:'reference',label:'Allocation reason / authority',type:'textarea',required:true},
    ]} onSave={v=>api.post('/founders/company-coverage/',body(v))}><Banner tone="info">This reduces the remaining founder request. It reserves only explicitly selected available cash and does not create a new receipt or journal.</Banner></FormDrawer>}
    {coverage && <FormDrawer title="Consume or release company funding coverage" eyebrow="Preserve allocation history" onClose={()=>setCoverage(null)} initial={{expense_id:'',reason:''}} fields={[
      {key:'expense_id',label:'Actual paid company expense ID (to consume)',type:'number'},{key:'reason',label:'Reason (required to release without an expense)',type:'textarea'},
    ]} onSave={v=>api.post(`/founders/company-coverage/${coverage.id}/resolve/`,v.expense_id ? {expense_id:Number(v.expense_id)} : {reason:v.reason})}/>}
    {pledge && <FormDrawer title="Record requested / promised funding" eyebrow="Planning only" onClose={() => setPledge(false)} initial={{ plan_id: plan, party_id: '', month: `${today().slice(0, 7)}-01`, currency: config.data?.base_currency ?? '', amount: '', status: 'requested', reference: '' }} fields={[
      { key: 'plan_id', label: 'Saved plan', type: 'select', options: [{ value: '', label: 'Select…' }, ...(plans.data?.results ?? []).map(p => ({ value: String(p.id), label: p.name }))] },
      { key: 'party_id', label: 'Participant', type: 'select', options: partyOptions(parties.data?.results) }, { key: 'month', label: 'Funding month', type: 'date' },
      { key: 'currency', label: 'Currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) },
      { key: 'amount', label: 'Amount', type: 'amount' }, { key: 'status', label: 'Planning status', type: 'select', options: [{ value: 'requested', label: 'Requested' }, { value: 'promised', label: 'Promised' }] }, { key: 'reference', label: 'Reference / notes' },
    ]} onSave={v => api.post('/founders/pledges/', body(v))} />}
    {designation && <FormDrawer title="Designate verified company funding" eyebrow="No second cash posting" onClose={() => setDesignation(false)} initial={{ receipt_id: '', plan_id: plan, reserve_id: '', month: `${today().slice(0, 7)}-01`, amount: '' }} fields={[
      { key: 'receipt_id', label: 'Verified company receipt', type: 'select', options: [{ value: '', label: 'Select…' }, ...(receipts.data?.results ?? []).map(r => ({ value: String(r.id), label: `#${r.id} · ${r.party_name} · ${money(r.amount, r.currency)}` }))] },
      { key: 'plan_id', label: 'Plan (choose this OR a reserve)', type: 'select', options: [{ value: '', label: 'Not a plan allocation' }, ...(plans.data?.results ?? []).map(p => ({ value: String(p.id), label: p.name }))] },
      { key: 'reserve_id', label: 'Reserve', type: 'select', options: [{ value: '', label: 'Not a reserve allocation' }, ...(reserves.data?.results ?? []).map(r => ({ value: String(r.id), label: r.name }))] },
      { key: 'month', label: 'Allocation month', type: 'date' }, { key: 'amount', label: 'Designated amount', type: 'amount' },
    ]} onSave={v => { const data = body(v); if (!v.plan_id) delete data.plan_id; if (!v.reserve_id) delete data.reserve_id; return api.post('/founders/designations/', data); }} />}
    {consume && <FormDrawer title="Consume designated funding once" eyebrow="Link the actual bank payment" onClose={() => setConsume(null)} initial={{ expense_id: '',amount:consume.remaining }} fields={[{ key: 'expense_id', label: 'Posted company-paid expense ID', type: 'number', required: true, hint: 'Bank, currency, schedule and remaining cost coverage are checked by the server.' },{key:'amount',label:'Funding amount to consume (partial allowed)',type:'amount',required:true}]} onSave={v => api.post(`/founders/designations/${consume.id}/consume/`, body(v))} />}
    {releaseConsumption && <FormDrawer title="Release funding allocation" eyebrow="No bank or expense reversal" onClose={()=>setReleaseConsumption(null)} initial={{reason:''}} fields={[{key:'reason',label:'Reason for releasing the cost allocation',type:'textarea',required:true}]} onSave={v=>api.post(`/founders/consumptions/${releaseConsumption}/reverse/`,v)}><Banner tone="warn">This releases the planning designation only. Any correction to the actual company payment requires its own guarded accounting reversal.</Banner></FormDrawer>}
    {releaseFunding && <FormDrawer title="Release unused retained funding" eyebrow="Planning allocation only" onClose={()=>setReleaseFunding(null)} initial={{amount:releaseFunding.value.remaining,reason:''}} fields={[{key:'amount',label:'Unused funding to release',type:'amount',required:true},{key:'reason',label:'Reason and authority',type:'textarea',required:true}]} onSave={v=>api.post(`/founders/designations/${releaseFunding.value.id}/release/`,{...v,client_key:releaseFunding.key})}><Banner tone="info">Consumed funding cannot be released here. Releasing unused funding preserves all payment history and creates no company cash movement.</Banner></FormDrawer>}
  </>;
}
