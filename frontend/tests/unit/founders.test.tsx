import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { FoundersApp } from '@/features/founders/FoundersApp';
import { CorporateDetail, CorporateDrawer } from '@/features/founders/Corporate';
import { PlannerPageContent, ContributionContent } from '@/features/founders/Planning';
import { PartiesPage } from '@/features/founders/Parties';
import { OwnershipPage } from '@/features/ownership/Ownership';
import { OwnershipApp } from '@/features/ownership/OwnershipApp';
import { SettlementDetail } from '@/features/founders/Personal';
import { makeUser, mockApi, renderWithAuth, viewerUser } from './helpers';

const page = <T,>(results: T[]) => ({ count: results.length, page: 1, page_size: 25, total_pages: 1, results });
const common = {
  '/auth/me/': makeUser(),
  '/accounting/config/': { base_currency: 'BDT', enabled_currencies: ['BDT'] },
  '/reference/currencies/': [{ code: 'BDT', symbol: '৳' }],
  '/founders/parties/': page([{id:1,name:'Founder A',is_founder:true,user:1,is_active:true},{id:2,name:'Investor',is_shareholder:true,user:null,is_active:true}]),
  '/accounting/accounts/': page([]), '/accounting/taxes/': page([]), '/banking/accounts/': page([{id:7,name:'Company bank',currency:'BDT'}]),
  '/founders/loans/': page([]), '/ownership/proposals/': page([]), '/founders/obligations/': page([]),
  '/founders/plans/': page([]), '/founders/reserves/': page([]), '/founders/transactions/': page([]),
  '/founders/pledges/': page([]), '/founders/designations/': page([]), '/founders/company-coverage/':page([]),
};

it('denies founder corporate screens to ordinary financial viewers', async () => {
  const calls = mockApi({...common,'/auth/me/':viewerUser});
  renderWithAuth(<FoundersApp section="contributions"/>, viewerUser);
  expect(await screen.findByText('Your role does not include founder finance.')).toBeInTheDocument();
  expect(calls.some(c => c.path.startsWith('/founders/transactions'))).toBe(false);
});

it('creates real participant records without treating them as shares or cash', async () => {
  const calls = mockApi({...common,'POST /founders/parties/': {id:3}});
  renderWithAuth(<PartiesPage/>);
  expect(screen.queryByText(/Provisional agreements can evolve before registration/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Add participant'}));
  expect(screen.queryByText(/Adding a participant does not issue shares/)).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText('Full / organization name'),'New partner');
  await userEvent.click(screen.getByRole('button',{name:'Save'}));
  await waitFor(()=>expect(calls.find(c=>c.method==='POST' && c.path==='/founders/parties/')?.body).toMatchObject({name:'New partner',user_id:null}));
});

it('allows an external shareholder to be selected for actual capital funding', async () => {
  mockApi(common);
  renderWithAuth(<CorporateDrawer kind="receipt" onClose={vi.fn()}/>);
  expect(await screen.findByRole('option',{name:'Investor'})).toBeInTheDocument();
});

it('requires a server preview and independent verifier before posting', async () => {
  const tx={id:5,kind:'receipt',classification:'pending',party:1,party_name:'Founder A',date:'2026-03-01',currency:'BDT',amount:'0.10',status:'recorded',created_by:1,notes:'',journal:null,snapshot:{}};
  const calls=mockApi({...common,'/founders/transactions/5/':tx,'/founders/evidence/':page([]),
    'POST /founders/transactions/5/preview/':{quote_fingerprint:'server-frozen-preview',fx_difference:'0',base_currency:'BDT',lines:[]}});
  renderWithAuth(<CorporateDetail id="5"/>);
  await userEvent.click(await screen.findByRole('button',{name:'Preview accounting'}));
  expect(await screen.findByRole('checkbox')).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Verify transaction'})).not.toBeInTheDocument();
  expect(calls.some(c=>c.path.endsWith('/verify/'))).toBe(false);
});

it('saves a backend-calculated forecast and displays exact annual timing', async () => {
  const snapshot={starts:'2026-01-01',months:12,base_currency:'BDT',complete:true,issues:[],rows:[{
    month:'2026-12-01',currency:'BDT',cost:'7200',cash_due:'7200',reserve_target:'0',reserve_coverage:'0',funding_target:'7200',founder_request:'7200',founders:{'1':'3600'},estimated_base_cost:'7200',estimated_rate:'1',rate_source:'base',sources:[],
  }]};
  const calls=mockApi({...common,'POST /founders/plans/':{id:10,name:'Annual forecast',snapshot}});
  renderWithAuth(<PlannerPageContent months={12}/>);
  await userEvent.clear(screen.getByLabelText('Starts'));
  await userEvent.type(screen.getByLabelText('Starts'),'2026-01-01');
  await userEvent.click(screen.getByRole('button',{name:'Save immutable forecast'}));
  expect(await screen.findByText(/Saved forecast #10/)).toBeInTheDocument();
  expect(screen.getByText(/3,600/)).toBeInTheDocument();
  expect(calls.find(c=>c.method==='POST' && c.path==='/founders/plans/')?.body).toMatchObject({months:12,mode:'founders'});
});

it('shows company coverage separately from verified personal contribution targets', async () => {
  mockApi({...common,'/founders/plans/':page([{id:10,name:'Partial funding'}]),'/founders/plans/10/progress/':[{
    month:'2026-02-01',currency:'BDT',founder_request:'6000',company_coverage:'2000',verified_designated:'500',remaining:'3500',remaining_founder_targets:{'1':'2000'},verified_by_founder:{'1':'500'},remaining_by_founder:{'1':'1500'},surplus_by_founder:{'1':'0'},
  }]});
  renderWithAuth(<ContributionContent/>);
  await screen.findByRole('option',{name:'Partial funding'});
  await userEvent.selectOptions(screen.getByLabelText('Saved plan'),'10');
  expect(await screen.findByText(/1,500.*due/)).toBeInTheDocument();
  expect(screen.getByRole('columnheader',{name:'Company coverage'})).toBeInTheDocument();
});

it('shows provisional ownership percentages clearly and preserves backend error feedback', async () => {
  mockApi({...common,'/ownership/register/':{provisional:{proposal_id:2,effective_date:'2026-03-01',weights:{'1':'40','2':'40','3':'20'}},classes:{}},'/ownership/capital/':[403,{error:{code:'denied',message:'Capital access denied',details:null,request_id:'x'}}]});
  renderWithAuth(<OwnershipPage section="overview"/>);
  expect(await screen.findByText('Capital access denied')).toBeInTheDocument();
  expect(screen.getAllByText('40%')).toHaveLength(2);
  expect(screen.getByText('20%')).toBeInTheDocument();
  expect(screen.queryByText(/not formally issued shares/)).not.toBeInTheDocument();
});

it('shows historical posted costs against the frozen foreign-currency estimate',async()=>{
  mockApi({...common,'/founders/plans/':page([{id:12,name:'USD estimate'}]),'/founders/plans/12/progress/':[{
    month:'2026-01-01',currency:'USD',base_currency:'BDT',founder_request:'20',company_coverage:'0',verified_designated:'0',remaining:'20',posted_costs:[{identity:'schedule:1:2026-01-15',name:'USD hosting',journal_id:'7c926c26-2319-4384-8d3c-fdfb439e0e59',actual_rate:'120.000000000000',actual_base_cost:'2400.00',estimated_base_cost:'2000.00',base_cost_variance:'400.00'}],
  }]});
  renderWithAuth(<ContributionContent/>);
  await screen.findByRole('option',{name:'USD estimate'});
  await userEvent.selectOptions(screen.getByLabelText('Saved plan'),'12');
  expect(await screen.findByRole('link',{name:/USD hosting/})).toHaveAttribute('href','/banking/journals/7c926c26-2319-4384-8d3c-fdfb439e0e59');
  expect(screen.getByRole('cell',{name:/2,400/})).toBeInTheDocument();
  expect(screen.getByRole('cell',{name:/2,000/})).toBeInTheDocument();
  expect(screen.getByRole('cell',{name:/^[^0-9]*400\.00$/})).toBeInTheDocument();
  expect(screen.getByText('120.000000000000')).toBeInTheDocument();
});

it('shows private settlement load errors instead of leaving an unexplained empty record',async()=>{
  mockApi({...common,'/founders/settlements/999/':[404,{error:{code:'not_found',message:'Settlement unavailable',details:null,request_id:'x'}}],'/founders/evidence/':page([])});
  renderWithAuth(<SettlementDetail id="999"/>);
  expect(await screen.findByText('Settlement unavailable')).toBeInTheDocument();
});

it('gives consent-only shareholders a scoped inbox without requesting the full register',async()=>{
  const user=makeUser({permissions:['ownership.consent']});
  const calls=mockApi({...common,'/auth/me/':user});
  renderWithAuth(<OwnershipApp section="history"/>,user);
  expect(await screen.findByRole('heading',{name:'Ownership requests'})).toBeInTheDocument();
  expect(calls.some(c=>c.path.startsWith('/ownership/register'))).toBe(false);
  expect(calls.some(c=>c.path.startsWith('/ownership/capital'))).toBe(false);
});

it('releases only the entered retained funding with a stable key and explicit reason',async()=>{
  const designation={id:5,receipt:1,reserve:1,plan:null,month:'2026-02-01',amount:'100',remaining:'40.00',consumptions:[]};
  const calls=mockApi({...common,'/founders/designations/':page([designation]),'POST /founders/designations/5/release/':{...designation,remaining:'20.00'}});
  renderWithAuth(<ContributionContent/>);
  await userEvent.click(await screen.findByRole('button',{name:'Release unused funding'}));
  await userEvent.clear(screen.getByLabelText('Unused funding to release'));
  await userEvent.type(screen.getByLabelText('Unused funding to release'),'20.00');
  await userEvent.type(screen.getByLabelText('Reason and authority'),'Authorized change to the funding plan');
  await userEvent.click(screen.getByRole('button',{name:'Save'}));
  await waitFor(()=>expect(calls.find(c=>c.method==='POST' && c.path==='/founders/designations/5/release/')?.body).toMatchObject({amount:'20.00',reason:'Authorized change to the funding plan',client_key:expect.any(String)}));
});
