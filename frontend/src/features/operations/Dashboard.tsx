'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Input, Select } from '@/components/ui/Input';
import { Spinner } from '@/components/ui/Spinner';
import { StatGrid } from '@/components/ui/StatGrid';
import { Screen } from '@/features/commerce/forms';
import { Card, today, useApi, useMoney } from '@/features/commerce/shared';
import { BreakdownChart, MonthlyChart, type MonthlyPoint } from '@/features/commerce/Charts';
import { HealthPanel } from '@/features/system/HealthPanel';
import { errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';

interface Metric {key:string;label:string;value:string|number;kind:'money'|'count'|'percent';route:string;sub:string;previous?:string;change_percent?:string|null}
interface Summary {configured:boolean;base_currency:string|null;from:string;to:string;metrics:Metric[];series:MonthlyPoint[];alerts:{tone:'info'|'warn';text:string;route:string|null}[];aging?:{receivable:Record<string,string>;payable:Record<string,string>}}
const bucketLabels:Record<string,string>={current:'Current','1_30':'1–30 days','31_60':'31–60 days','61_90':'61–90 days', '90_plus':'90+ days',unallocated:'Unallocated / opening'};

export function ExecutiveDashboard() {
  const {can}=useAuth();const money=useMoney();const [range,setRange]=useState('year');const [from,setFrom]=useState(today());const [to,setTo]=useState(today());
  const query=useApi<Summary>(`/reporting/dashboard/?range=${range}${range==='custom'?`&from=${from}&to=${to}`:''}`);
  const data=query.data;
  return <Screen eyebrow="Overview" title="Dashboard" description={data?.configured?`Posted financial activity · ${data.from} — ${data.to}`:'Authoritative company activity and installation status.'}
    actions={<div className="flex flex-wrap gap-2"><Select aria-label="Dashboard period" value={range} onChange={e=>{if(e.target.value==='custom'&&data){setFrom(data.from);setTo(data.to);}setRange(e.target.value);}}>
      <option value="month">Current month</option><option value="previous">Previous month</option><option value="quarter">Current quarter</option><option value="year">Fiscal year to date</option><option value="custom">Custom range</option></Select>
      {range==='custom'&&<><Input aria-label="Dashboard from" type="date" value={from} onChange={e=>setFrom(e.target.value)} /><Input aria-label="Dashboard to" type="date" value={to} onChange={e=>setTo(e.target.value)} /></>}</div>}>
    {query.loading&&!data&&<Spinner />}{Boolean(query.error)&&<Banner tone="err">{errorMessage(query.error)}</Banner>}
    {data&&!data.configured&&<Banner tone="info">Configure the company profile before recording financial activity. {can('company.edit')&&<Link href="/settings/company">Open company setup</Link>}</Banner>}
    {data?.metrics.length ? <StatGrid minWidth={180} balancedSeven stats={data.metrics.map(m=>({label:m.label,value:<Link className="text-inherit hover:text-lk" href={`${m.route}${m.route.includes('?')?'&':'?'}from=${data.from}&to=${data.to}`}>{m.kind==='money'?money(String(m.value),data.base_currency??undefined):m.kind==='percent'?`${m.value}%`:m.value}</Link>,
      sub:<>{m.sub}{m.change_percent!==undefined&&<span className="block">{m.change_percent===null?'No previous-period comparison base':`${m.change_percent}% vs previous equal period`}</span>}</>,accentBar:true,tone:m.key==='net_profit'&&String(m.value).startsWith('-')?'err':'default'}))} />:null}
    {data?.alerts.map((alert,i)=><Banner key={i} tone={alert.tone}>{alert.text}{alert.route&&<> <Link href={alert.route}>Review sources</Link></>}</Banner>)}
    {data?.metrics.length ? <>
      <div className="grid gap-[18px] xl:grid-cols-2"><MonthlyChart title="Revenue vs expenses" subtitle="Recognized posted GL · selected range" points={data.series} series={[{key:'revenue',label:'Revenue'},{key:'expenses',label:'Expenses'}]} currency={data.base_currency??undefined} />
        <MonthlyChart title="Profit trend" subtitle="Revenue less all posted expenses · no forecast amounts" points={data.series} series={[{key:'profit',label:'Net profit / (loss)'}]} currency={data.base_currency??undefined} /></div>
      <div className="grid gap-[18px] xl:grid-cols-2">{(['receivable','payable'] as const).map(kind=><BreakdownChart key={kind} aging title={kind==='receivable'?'Receivables aging':'Payables aging'} subtitle={`Historical GL at ${data.to}; unallocated balances disclosed separately`} rows={Object.entries(data.aging?.[kind]??{}).map(([key,amount])=>({label:bucketLabels[key]??key,amount}))} currency={data.base_currency??undefined} />)}</div>
      <Card title="Financial definitions"><p className="m-0 p-4 text-[12.5px] text-tx2">Recognized revenue and expenses come from posted journals. Dispatch, invoices, approvals, budgets, funding forecasts and personal founder settlements retain their distinct accounting roles. Budget utilization uses current approved allocations for the selected months.</p></Card>
    </>:null}
    <HealthPanel />
  </Screen>;
}
