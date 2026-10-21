'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Input, Select } from '@/components/ui/Input';
import { StatGrid } from '@/components/ui/StatGrid';
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/Table';
import { DateFilters, JournalLink, useRange } from '@/features/accounting/shared';
import { FormDrawer, Screen } from '@/features/commerce/forms';
import { ListPanel, sumDecimals, useApi, useMoney } from '@/features/commerce/shared';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';

interface Movement {id:string;number:string;posting_date:string;description:string;cash_debit:string;cash_credit:string}
interface Review {id:number;version:number;allocations:{category:string;amount:string}[];reason:string}
interface Statement {base_currency:string;opening:string;closing:string;operating:string;investing:string;financing:string;opening_cutover:string;unclassified:string;unclassified_count:number;transfer_fx_effect:string;classified_difference:string}
const activities=[['operating','Operating'],['investing','Investing'],['financing','Financing'],['opening_cutover','Opening / cutover'],['unclassified','Unclassified']];

function ReviewDrawer({movement,onClose}:{movement:Movement;onClose:()=>void}) {
  const history=useApi<Page<Review>>(`/reporting/cash-reviews/?journal_id=${movement.id}`);
  const net=sumDecimals([movement.cash_debit,`-${movement.cash_credit}`]);
  const [rows,setRows]=useState([{category:'unclassified',amount:net}]);const [initial]=useState(JSON.stringify(rows));
  return <FormDrawer title="Review cash-flow classification" eyebrow={movement.number} onClose={onClose} width={740}
    description="Classify the actual signed base-currency cash movement. Splits must equal the exact net amount. A new review version is retained; no journal, payment or bank balance changes."
    initial={{reason:''}} extraDirty={JSON.stringify(rows)!==initial} fields={[{key:'reason',label:'Source evidence and classification rationale',type:'textarea',required:true}]}
    onSave={v=>{if(!history.data)throw new Error('Load the retained review history before saving.');return api.post('/reporting/cash-reviews/',{journal_id:movement.id,expected_version:history.data.results[0]?.version??0,allocations:rows,reason:v.reason});}}>
    <Table><THead><TR><TH>Activity</TH><TH>Signed base amount</TH><TH /></TR></THead><TBody>{rows.map((row,i)=><TR key={i}>
      <TD><Select aria-label={`Allocation ${i+1} activity`} value={row.category} onChange={e=>setRows(v=>v.map((r,n)=>n===i?{...r,category:e.target.value}:r))}>{activities.map(([value,label])=><option key={value} value={value}>{label}</option>)}</Select></TD>
      <TD><Input aria-label={`Allocation ${i+1} amount`} inputMode="decimal" value={row.amount} onChange={e=>setRows(v=>v.map((r,n)=>n===i?{...r,amount:e.target.value}:r))} /></TD>
      <TD><Button size="xs" disabled={rows.length===1} onClick={()=>setRows(v=>v.filter((_,n)=>n!==i))}>Remove</Button></TD>
    </TR>)}</TBody></Table><Button size="sm" disabled={rows.length>=20} onClick={()=>setRows(v=>[...v,{category:'unclassified',amount:''}])}>Add allocation</Button>
    <ListPanel<Review> path={`/reporting/cash-reviews/?journal_id=${movement.id}`} title="Retained classifications" columns={[{key:'version',label:'Version',render:r=>`v${r.version}`},{key:'reason',label:'Evidence',render:r=>r.reason}]} />
  </FormDrawer>;
}

export function CashFlowPage() {
  const {can}=useAuth();const range=useRange();const money=useMoney();const [review,setReview]=useState<Movement|null>(null);
  const query=useApi<Statement>(`/accounting/reports/cf/?${range.query}`);const data=query.data;
  const values:[keyof Statement,string][]=[['opening','Opening cash / bank'],['operating','Operating cash flow'],['investing','Investing cash flow'],['financing','Financing cash flow'],['opening_cutover','Opening / cutover adjustments'],['unclassified','Unclassified movement'],['transfer_fx_effect','Transfer FX effect'],['closing','Closing cash / bank'],['classified_difference','Reconciliation difference']];
  return <Screen title="Cash Flow" eyebrow="Reports & Analytics" description="Posted cash movement, source classification and retained reviews. Internal transfers are eliminated; opening adjustments and FX remain separate."
    actions={can('reports.export')&&<Link className="inline-flex h-[34px] items-center border border-bd2 bg-sf px-3" href={`/api/v1/accounting/reports/cf/?${range.query}&export=csv`}>Export CSV</Link>}>
    <DateFilters from={range.from} to={range.to} onFrom={range.setFrom} onTo={range.setTo} />
    {Boolean(query.error)&&<Banner tone="err">{errorMessage(query.error)}</Banner>}
    <StatGrid stats={values.map(([key,label])=>({label,value:data?money(String(data[key]),data.base_currency):'—'}))} />
    {data&&data.unclassified_count>0&&<Banner tone="warn">{data.unclassified_count} cash movements require source review. These amounts are disclosed as unclassified; they are included in the reconciliation.</Banner>}
    <ListPanel<Movement> path={`/reporting/cash-movements/?${range.query}`} title="Posted external cash movements" columns={[
      {key:'journal',label:'Source',render:m=><JournalLink id={m.id}>{m.number}</JournalLink>},{key:'date',label:'Date',render:m=>formatDate(m.posting_date)},
      {key:'memo',label:'Description',render:m=>m.description},{key:'in',label:'Cash debit',align:'right',render:m=>money(m.cash_debit,data?.base_currency)},
      {key:'out',label:'Cash credit',align:'right',render:m=>money(m.cash_credit,data?.base_currency)},
      {key:'review',label:'Classification',render:m=>can('reports.classify')&&<Button size="xs" onClick={()=>setReview(m)}>Review activity</Button>},
    ]} />{review&&<ReviewDrawer movement={review} onClose={()=>setReview(null)} />}
  </Screen>;
}
