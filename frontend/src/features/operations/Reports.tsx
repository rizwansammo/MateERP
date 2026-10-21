'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Panel } from '@/components/ui/Panel';
import { Spinner } from '@/components/ui/Spinner';
import { Input, Select } from '@/components/ui/Input';
import { Field } from '@/components/ui/Field';
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/Table';
import { Pager, SearchBox, TableState, TableToolbar } from '@/components/ui/TableKit';
import { DateFilters, useRange } from '@/features/accounting/shared';
import { StatementsPage, LedgerPage } from '@/features/accounting/Reports';
import { Screen } from '@/features/commerce/forms';
import { Gate, useApi, useMoney } from '@/features/commerce/shared';
import { errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { useDebounced } from '@/lib/useDebounced';
import { CashFlowPage } from './CashFlow';

interface ReportDefinition {key:string;title:string;group:string;description:string;route:string;permissions:string[]}
interface Column {key:string;label:string;kind:'text'|'date'|'money'|'base_money'|'quantity'}
type Row=Record<string,string|number|boolean|null>;
interface Result extends Page<Row> {report:string;base_currency:string;columns:Column[];note:string;summary:Record<string,unknown>}
const groups=[['all','All reports'],['financial','Financial'],['sales','Sales'],['founder','Founder'],['operational','Operational']];

const FILTERS = {
  customer_id: {label:'Customer',endpoint:'/sales/customers/'},
  vendor_id: {label:'Vendor',endpoint:'/purchasing/vendors/'},
  item_id: {label:'Product / service',endpoint:'/sales/items/'},
  location_id: {label:'Location',endpoint:'/inventory/locations/'},
  account_id: {label:'Account',endpoint:'/accounting/accounts/'},
} as const;
type FilterKey=keyof typeof FILTERS;
const reportFilters:Record<string,FilterKey[]>={income:['account_id'],expense:['account_id'],ar:['customer_id'],ap:['vendor_id'],customer:['customer_id'],product:['customer_id','item_id'],vendors:['vendor_id'],locations:['location_id','item_id'],'low-stock':['item_id'],receiving:['vendor_id','location_id','item_id'],recurring:['customer_id'],bank:['account_id'],tax:['account_id']};
const currencyReports=['customer','product','vendors','history','recurring','bank'];

function SourceFilter({field,value,onChange}:{field:FilterKey;value:string;onChange:(value:string)=>void}) {
  const definition=FILTERS[field];const [search,setSearch]=useState('');const term=useDebounced(search,250);
  const query=useApi<Page<{id:number;name:string;code?:string}>>(`${definition.endpoint}?page_size=100&search=${encodeURIComponent(term)}`);
  return <Field label={definition.label} htmlFor={`report-filter-${field}`}><div className="flex flex-col gap-1">
    <Input controlSize="sm" aria-label={`Find ${definition.label.toLowerCase()}`} value={search} onChange={e=>setSearch(e.target.value)} placeholder="Find options…" />
    <Select id={`report-filter-${field}`} controlSize="sm" aria-label={`Filter ${definition.label.toLowerCase()}`} value={value} onChange={e=>onChange(e.target.value)}>
      <option value="">All</option>{query.data?.results.map(row=><option key={row.id} value={row.id}>{row.code?`${row.code} · `:''}{row.name}</option>)}
    </Select>{Boolean(query.error)&&<span role="alert" className="text-err">{errorMessage(query.error)}</span>}
  </div></Field>;
}

function ReportLibrary() {
  const query=useApi<ReportDefinition[]>('/reporting/catalog/');const [group,setGroup]=useState('all');const [search,setSearch]=useState('');
  const definitions=query.data?.filter(r=>(group==='all'||r.group===group)&&`${r.title} ${r.description}`.toLowerCase().includes(search.toLowerCase()));
  return <Screen title="Reports & Analytics" eyebrow="Management" description="Recognized financials, operational sources and approved plans retain their distinct meanings. Reports and exports enforce your stored permissions.">
    {Boolean(query.error)&&<Banner tone="err">{errorMessage(query.error)}</Banner>}
    <div className="flex flex-wrap items-center gap-2"><SearchBox value={search} onChange={setSearch} placeholder="Find a report…" />{groups.map(([key,label])=><button type="button" key={key} onClick={()=>setGroup(key!)} className={`h-[30px] border px-3 text-[12px] ${group===key?'border-ac bg-infos text-lk':'border-bd2 bg-sf text-tx2'}`}>{label}</button>)}</div>
    {query.loading&&<Spinner />}
    <div className="grid gap-[18px] md:grid-cols-2 xl:grid-cols-3">{definitions?.map(r=><Link key={r.key} href={r.route} className="border border-bd bg-sf p-4 text-inherit hover:border-ac hover:bg-sfh hover:no-underline">
      <span className="mb-2 block text-[10.5px] font-semibold uppercase tracking-[.1em] text-tx3">{r.group}</span><h2 className="m-0 text-[13.5px] font-semibold">{r.title}</h2><p className="mb-0 mt-2 text-[12.5px] leading-relaxed text-tx2">{r.description}</p>
    </Link>)}</div>
    {query.data&&!definitions?.length&&<Banner tone="info">No authorized reports match this selection.</Banner>}
  </Screen>;
}

function DataReport({which}:{which:string}) {
  const range=useRange();const {can}=useAuth();const money=useMoney();const [page,setPage]=useState(1);const [search,setSearch]=useState('');const term=useDebounced(search,250);
  const [filters,setFilters]=useState<Partial<Record<FilterKey|'currency',string>>>({});const [sort,setSort]=useState('');
  const catalogue=useApi<ReportDefinition[]>('/reporting/catalog/');
  const allowed=catalogue.data?.find(r=>r.key===which);
  const currencies=useApi<{enabled_currencies:string[]}>(allowed&&currencyReports.includes(which)?'/accounting/config/':null);
  const params=`${range.query}&search=${encodeURIComponent(term)}&sort=${encodeURIComponent(sort)}&${new URLSearchParams(Object.entries(filters).filter(([,value])=>Boolean(value))).toString()}`;
  const query=useApi<Result>(allowed?`/reporting/reports/${which}/?${params}&page=${page}&page_size=25`:null);const data=query.data;
  const format=(row:Row,column:Column)=>{
    const value=row[column.key];if(value===null||value===undefined)return '—';
    if(column.kind==='money')return money(String(value),typeof row.currency==='string'?row.currency:data?.base_currency);
    if(column.kind==='base_money')return money(String(value),data?.base_currency);
    if(column.kind==='date')return formatDate(String(value));
    return typeof value==='boolean'?(value?'Yes':'No'):String(value);
  };
  if(catalogue.loading)return <Spinner />;
  if(catalogue.error)return <Banner tone="err">{errorMessage(catalogue.error)}</Banner>;
  return <Gate allow={Boolean(allowed)} what="this report"><Screen title={allowed?.title??'Report'} eyebrow="Reports & Analytics" description={allowed?.description}
    actions={can('reports.export')&&<Link className="inline-flex h-[34px] items-center border border-bd2 bg-sf px-3" href={`/api/v1/reporting/reports/${which}/?${params}&export=csv`}>Export CSV</Link>}>
    <DateFilters from={range.from} to={range.to} onFrom={v=>{setPage(1);range.setFrom(v);}} onTo={v=>{setPage(1);range.setTo(v);}} />
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{(reportFilters[which]??[]).map(field=><SourceFilter key={field} field={field} value={filters[field]??''} onChange={value=>{setPage(1);setFilters(v=>({...v,[field]:value}));}} />)}
      {currencyReports.includes(which)&&<Field label="Transaction currency" htmlFor="report-filter-currency"><Select id="report-filter-currency" aria-label="Filter currency" value={filters.currency??''} onChange={e=>{setPage(1);setFilters(v=>({...v,currency:e.target.value}));}}><option value="">All currencies (separate amounts)</option>{currencies.data?.enabled_currencies.map(currency=><option key={currency}>{currency}</option>)}</Select></Field>}
    </div>
    {Boolean(query.error)&&<Banner tone="err">{errorMessage(query.error)}</Banner>}{data?.note&&<Banner tone="info">{data.note}</Banner>}
    <Panel><TableToolbar><SearchBox value={search} onChange={v=>{setPage(1);setSearch(v);}} placeholder="Filter report records…" /></TableToolbar>
      <Table><THead><TR>{data?.columns.map(c=><TH key={c.key} align={['money','base_money','quantity'].includes(c.kind)?'right':'left'}><button type="button" aria-label={`Sort by ${c.label}`} onClick={()=>{setPage(1);setSort(v=>v===c.key?`-${c.key}`:c.key);}} className="bg-transparent text-inherit">{c.label}{sort===c.key?' ↑':sort===`-${c.key}`?' ↓':''}</button></TH>)}<TH>Source</TH></TR></THead><TBody>
        <TableState loading={query.loading} error={query.error?errorMessage(query.error):null} empty={!data?.results.length} colSpan={(data?.columns.length??1)+1}>
          {data?.results.map((row,i)=><TR key={`${row.id??i}-${String(row.currency??'')}`}>
            {data.columns.map(c=><TD key={c.key} align={['money','base_money','quantity'].includes(c.kind)?'right':'left'}>{format(row,c)}</TD>)}
            <TD>{typeof row.route==='string'&&<Link href={row.route}>View source</Link>}</TD>
          </TR>)}
        </TableState></TBody></Table>
      {data&&<Pager page={data.page} totalPages={data.total_pages} count={data.count} pageSize={data.page_size} onPage={setPage} />}
    </Panel>
  </Screen></Gate>;
}

export function ReportsApp({which}:{which?:string}) {
  const {can}=useAuth();
  if(!which)return <ReportLibrary />;
  return <Gate allow={can('finance.view')}>{which==='cash-flow'||which==='cf'?<CashFlowPage />:['pnl','bs','tb'].includes(which)?<StatementsPage which={which} />:which==='ledger'?<LedgerPage />:<DataReport which={which} />}</Gate>;
}
