import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { DatedPriceButton } from '@/features/commerce/lines';
import { ExecutiveDashboard } from '@/features/operations/Dashboard';
import { ReportsApp } from '@/features/operations/Reports';
import { CatalogApp } from '@/features/operations/Catalog';
import { InventoryApp } from '@/features/operations/Inventory';
import { OnboardingPage } from '@/features/operations/Onboarding';
import { OrderDetail } from '@/features/operations/Fulfillment';
import { AssetsApp } from '@/features/operations/Assets';
import { BudgetsApp } from '@/features/operations/Budgets';
import { PurchaseOrdersPage } from '@/features/operations/Procurement';
import { makeUser, mockApi, renderWithAuth, viewerUser } from './helpers';

const page = <T,>(results: T[]) => ({ count: results.length, page: 1, page_size: 25, total_pages: 1, results });
const common = {
  '/auth/me/': makeUser(),
  '/accounting/config/': { base_currency: 'BDT', enabled_currencies: ['BDT'] },
  '/reference/currencies/': [{ code: 'BDT', symbol: '৳' }],
};

it('renders real inventory summary values without adding unlike units together', async () => {
  mockApi({ ...common,
    '/inventory/summary/': {base_currency:'BDT',as_of:'2026-10-21',stock_value:'1000',tracked_items:2,nonstock_items:1,
      unit_totals:[{unit:'EA',quantity:'10'},{unit:'KG',quantity:'2'}],low_stock_count:1,
      low_stock:[{id:8,code:'WIDGET',name:'Widget',quantity:'10',unit:'EA'}],locations:3,movements_this_month:4,
      by_item:[{label:'Widget',amount:'1000'}]},
    '/inventory/valuation/': {...page([]),reconciliation:{difference:'0',stock_value:'1000',gl_value:'1000'}},
    '/inventory/movements/':page([]), '/inventory/counts/':page([]),
  });
  renderWithAuth(<InventoryApp section="overview" />);
  expect(await screen.findByText('Unit groups on hand')).toBeVisible();
  expect(screen.getByText('Quantities remain separate by unit')).toBeVisible();
  expect(screen.getByText('Stock value by item')).toBeVisible();
  expect(screen.getByRole('link',{name:'Widget'})).toHaveAttribute('href','/inventory/items/8');
  expect(screen.queryByText('12 EA')).not.toBeInTheDocument();
});

it('uses server asset carrying values without losing monetary precision', async () => {
  mockApi({...common,'/assets/register/':page([{id:'asset-1',tag:'SERVER-1',name:'Historical server',category:'Servers',in_service_date:'2026-01-01',cost:'9007199254740993.01',accumulated:'1.01',book_value:'9007199254740992.00',status:'active'}]),
    '/assets/register/reconciliation/':{cost:'9007199254740993.01',cost_difference:'0',depreciation:'1.01',depreciation_difference:'0'}});
  renderWithAuth(<AssetsApp section="register" />);
  expect(await screen.findByText('BDT 9,007,199,254,740,992.00')).toBeVisible();
  expect(screen.getByRole('link',{name:'SERVER-1'})).toHaveAttribute('href','/assets/register/asset-1');
});

it('creates real cost-center configuration and preserves its historical identity on deactivation', async () => {
  const calls=mockApi({...common,'/budgeting/cost-centers/':page([{id:8,code:'HOST',name:'Hosting',description:'Infrastructure',department:'Engineering',owner_reference:'Operations',is_active:true,categories:[]}]),'/budgeting/spending/':page([]),'PATCH /budgeting/cost-centers/8/':{id:8,is_active:false}});
  renderWithAuth(<BudgetsApp section="costcenters" />);
  await userEvent.click(await screen.findByRole('button',{name:'Edit'}));
  await userEvent.click(screen.getByRole('checkbox',{name:'Active'}));
  await userEvent.click(screen.getByRole('button',{name:'Save'}));
  await waitFor(()=>expect(calls.find(c=>c.method==='PATCH'&&c.path==='/budgeting/cost-centers/8/')?.body).toMatchObject({code:'HOST',is_active:false}));
});

it('compares retained original and revised budgets against backend posted actuals', async () => {
  const calls=mockApi({...common,'/budgeting/budgets/4/':{id:4,name:'Hosting plan',fiscal_start:'2026-01-01',fiscal_end:'2026-12-31',active_revision_id:7,original_revision_id:6,is_archived:false},
    '/budgeting/revisions/':page([{id:7,version:2,status:'approved',notes:'Revised hosting allocation',lines:[]}]),
    '/budgeting/revisions/7/comparison/':[{id:10,month:'2026-10-01',account_code:'6100',account_name:'Operating costs',category:'operating',cost_center:'HOST',original:'10000',revised:'10000',actual:'8000',remaining:'2000',variance:'-2000',over_budget:false}],
    '/budgeting/revisions/7/actuals/':page([])});
  renderWithAuth(<BudgetsApp section="budgets" id="4" />);
  expect(await screen.findByText('BDT 8,000.00')).toBeVisible();expect(screen.getByText('BDT 2,000.00')).toBeVisible();
  expect(screen.getByText('80%')).toBeVisible();
  await userEvent.click(screen.getByRole('button',{name:'Source details'}));
  await waitFor(()=>expect(calls.some(c=>c.path.includes('/budgeting/revisions/7/actuals/?line_id=10'))).toBe(true));
});

it('shows documented control events separately from dispatch and never invents revenue', async () => {
  mockApi({ ...common, '/sales/orders/9/': { id: 9, number: 'SO-9', customer_name: 'Client', customer_reference: 'AGREEMENT-9', status: 'confirmed', currency: 'BDT', total: '2000', order_date: '2026-10-01', lines: [] },
    '/billing/fulfillment/policies/': page([{ id: 1, trigger: 'control_transfer', contract_reference: 'CONTROL-9', net_contract: '2000', controlled_quantity: '0', snapshot: { item_code: 'SKU-9', currency: 'BDT', quantity: '10' } }]),
    '/billing/fulfillment/dispatches/': page([{ id: 'dispatch-1', date: '2026-10-02', reference: 'DISPATCH-9', evidence: 'Company-owned transit', quantity: '10' }]),
    '/billing/fulfillment/control-transfers/': page([]), '/billing/fulfillment/returns/': page([]), '/billing/fulfillment/recalls/': page([]),
  });
  renderWithAuth(<OrderDetail id="9" />);
  expect(await screen.findByText('DISPATCH-9')).toBeVisible();
  expect(await screen.findByText('None — company-owned transit')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Transfer control' })).toBeVisible();
  expect(screen.getByText('0 / 10')).toBeVisible();
});

it('submits control evidence and exact decimal quantities to the real source API', async () => {
  const calls = mockApi({ ...common, '/sales/orders/9/': { id: 9, number: 'SO-9', customer_name: 'Client', status: 'confirmed', currency: 'BDT', total: '2000', order_date: '2026-10-01', lines: [] },
    '/billing/fulfillment/policies/': page([{ id: 1, trigger: 'control_transfer', contract_reference: 'CONTROL-9', net_contract: '2000', controlled_quantity: '0', snapshot: { item_code: 'SKU-9', currency: 'BDT', quantity: '10' } }]),
    '/billing/fulfillment/dispatches/': page([]), '/billing/fulfillment/control-transfers/': page([]), '/billing/fulfillment/returns/': page([]), '/billing/fulfillment/recalls/': page([]),
    '/inventory/locations/': page([{ id: 3, code: 'MAIN', name: 'Warehouse' }]), 'POST /billing/fulfillment/control-transfers/': { id: 'posted-control' },
  });
  renderWithAuth(<OrderDetail id="9" />);
  await userEvent.click(await screen.findByRole('button', { name: 'Transfer control' }));
  await userEvent.type(screen.getByLabelText('Quantity'), '1.234567');
  await userEvent.selectOptions(screen.getByLabelText('Stock location'), '3');
  await userEvent.type(screen.getByLabelText('Source reference'), 'ACCEPTED-1');
  await userEvent.type(screen.getByLabelText('Evidence / acceptance reference'), 'Signed customer acceptance');
  await userEvent.click(screen.getByRole('button', { name: 'Record event' }));
  await waitFor(() => expect(calls.find(c => c.method === 'POST' && c.path === '/billing/fulfillment/control-transfers/')?.body).toMatchObject({
    quantity: '1.234567', policy_id: 1, location_id: 3, reference: 'ACCEPTED-1', evidence: 'Signed customer acceptance',
  }));
});

it('shows server-priced catalog values and keeps legacy identities visible', async () => {
  const calls = mockApi({ ...common, '/catalog/items/': page([{
    id: 12, code: 'LEGACY-12', name: 'Existing service', description: 'Retained identity', unit: 'hr',
    currency: 'BDT', unit_price: '9007199254740993.01', is_active: true, profile: null,
  }]) });
  renderWithAuth(<CatalogApp section="products" />);
  expect(await screen.findByText('BDT 9,007,199,254,740,993.01')).toBeVisible();
  expect(screen.getByRole('link', { name: 'LEGACY-12' })).toHaveAttribute('href', '/catalog/products/12');
  expect(calls.some(c => c.path.includes('kind=product'))).toBe(true);
});

it('preserves decimal strings when creating a dated price revision', async () => {
  const calls = mockApi({ ...common, '/catalog/items/12/': { id: 12, code: 'SKU-12', name: 'Server product',
    unit: 'EA', currency: 'BDT', unit_price: '0', is_active: true, profile: null },
    '/catalog/items/12/prices/': page([]), 'POST /catalog/items/12/prices/': { id: 1 },
  });
  renderWithAuth(<CatalogApp section="pricing" id="12" />);
  await userEvent.click(await screen.findByRole('button', { name: 'Add price revision' }));
  await userEvent.type(screen.getByLabelText('Unit price'), '123.456789');
  await userEvent.type(screen.getByLabelText('Revision reason'), 'Reviewed new supplier quotation');
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(calls.find(c => c.method === 'POST' && c.path === '/catalog/items/12/prices/')?.body)
    .toMatchObject({ value: '123.456789', purpose: 'sale', reason: 'Reviewed new supplier quotation' }));
});

it('shows persistent purchase order totals without pretending approval posts a liability', async () => {
  mockApi({ ...common, '/purchasing/orders/': page([{ id: 9, number: 'PO-00009', vendor_name: 'Supplier', date: '2026-10-01',
    status: 'approved', revision: 2, total: '12345.67', currency: 'BDT' }]) });
  renderWithAuth(<PurchaseOrdersPage />);
  expect(await screen.findByText('BDT 12,345.67')).toBeVisible();
  expect(screen.getByRole('link', { name: 'PO-00009' })).toHaveAttribute('href', '/purchases/orders/9');
  expect(screen.getByText(/Order approval creates no ledger entry/)).toBeVisible();
});

it('discloses stock/GL differences rather than displaying a fake reconciled result', async () => {
  mockApi({ ...common, '/inventory/valuation/': { ...page([]), reconciliation: {
    currency: 'BDT', stock_value: '2250', gl_value: '2200', difference: '50',
  } } });
  renderWithAuth(<InventoryApp section="valuation" />);
  expect(await screen.findByText('BDT 50.00')).toBeVisible();
  expect(screen.getByText('BDT 2,250.00')).toBeVisible();
});

it('keeps historical original and recognition dates distinct and links to the real expense', async () => {
  mockApi({ ...common, '/accounting/historical-records/': page([{ id: 1, external_reference: 'HIST-1',
    original_date: '2026-01-05', description: 'Startup hosting', currency: 'BDT', amount: '1000',
    payment_source: 'Founder payment', funding_classification: 'founder_expense', pre_registration: true,
    treatment: { mode: 'reconstructed', status: 'approved', recognition_date: '2026-10-01', expense_id: 42 },
  }]) });
  renderWithAuth(<OnboardingPage />);
  expect(await screen.findByText('HIST-1')).toBeVisible();
  expect(screen.getByText(/Pre-registration — no automatic corporate recognition/)).toBeVisible();
  expect(screen.getByRole('link', { name: 'Expense workflow' })).toHaveAttribute('href', '/purchases/expenses/42');
});

it('denies historical onboarding to ordinary financial viewers without fetching its records', async () => {
  const calls = mockApi({ ...common, '/auth/me/': viewerUser });
  renderWithAuth(<OnboardingPage />, viewerUser);
  expect(await screen.findByText('Your role does not include reviewed historical onboarding.')).toBeVisible();
  expect(calls.some(c => c.path.startsWith('/accounting/historical-records/'))).toBe(false);
});


it('applies a dated server quote as a decimal string and rejects mismatched tax mode', async () => {
  const apply=vi.fn();let includesTax=false;
  const calls=mockApi({...common,'POST /catalog/items/12/quote/':()=>({unit_price:'9007199254740993.123456',includes_tax:includesTax})});
  renderWithAuth(<DatedPriceButton itemId="12" date="2026-10-21" currency="BDT" quantity="1.25" includesTax={false} onApply={apply} />);
  await userEvent.click(screen.getByRole('button',{name:'Use dated price'}));
  await waitFor(()=>expect(apply).toHaveBeenCalledWith('9007199254740993.123456'));
  expect(calls.find(c=>c.path==='/catalog/items/12/quote/')?.body).toMatchObject({date:'2026-10-21',currency:'BDT',quantity:'1.25',purpose:'sale'});
  apply.mockClear();includesTax=true;
  await userEvent.click(screen.getByRole('button',{name:'Use dated price'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('includes tax');
  expect(apply).not.toHaveBeenCalled();
});

it('uses stored report permissions and never fetches a forbidden financial projection', async () => {
  const calls=mockApi({...common,'/reporting/catalog/':[]});
  renderWithAuth(<ReportsApp which="history" />);
  expect(await screen.findByText('Your role does not include this report.')).toBeVisible();
  expect(calls.some(c=>c.path.startsWith('/reporting/reports/history/'))).toBe(false);
});

it('filters and sorts a paginated report through the backend and preserves export filters', async () => {
  const calls=mockApi({...common,'/reporting/catalog/':[{key:'customer',title:'Invoicing by Customer',description:'Actual issued sources',group:'sales',route:'/reports/customer',permissions:['finance.view']}],
    '/sales/customers/':page([{id:7,name:'Client Seven'}]),
    '/reporting/reports/customer/':{...page([{id:7,name:'Client Seven',currency:'BDT',net:'9007199254740993.01',route:'/sales/customers/7'}]),base_currency:'BDT',note:'Invoicing remains distinct from revenue',columns:[{key:'name',label:'Customer',kind:'text'},{key:'net',label:'Net invoiced',kind:'money'}],summary:{}}});
  renderWithAuth(<ReportsApp which="customer" />);
  expect(await screen.findByText('BDT 9,007,199,254,740,993.01')).toBeVisible();
  await userEvent.selectOptions(screen.getByLabelText('Filter customer'),'7');
  await userEvent.click(screen.getByRole('button',{name:'Sort by Net invoiced'}));
  await waitFor(()=>expect(calls.some(c=>c.path.startsWith('/reporting/reports/customer/?')&&c.path.includes('customer_id=7')&&c.path.includes('sort=net'))).toBe(true));
  expect(screen.getByRole('link',{name:'Export CSV'}).getAttribute('href')).toContain('customer_id=7');
  expect(screen.getByRole('link',{name:'View source'})).toHaveAttribute('href','/sales/customers/7');
});

it('shows an honest restricted dashboard without financial charts or invented metrics', async () => {
  mockApi({...common,'/reporting/dashboard/':{configured:true,base_currency:'BDT',from:'2026-01-01',to:'2026-10-21',metrics:[],series:[],alerts:[{tone:'info',text:'Your role does not include financial KPIs.',route:null}]}});
  renderWithAuth(<ExecutiveDashboard />);
  expect(await screen.findByText('Your role does not include financial KPIs.')).toBeVisible();
  expect(screen.queryByText('Revenue vs expenses')).not.toBeInTheDocument();
});


it('sends the retained correction UUID and signed cost without converting either to floating point',async()=>{
  const original='11111111-1111-4111-8111-111111111111';
  const calls=mockApi({...common,'/inventory/valuation/':{...page([]),reconciliation:{stock_value:'1000',gl_value:'1000',difference:'0'}},
    '/inventory/counts/':page([]),'/inventory/movements/':page([{id:original,date:'2026-01-01',kind:'receipt',reason:'Original valued delivery'}]),
    '/catalog/items/':page([{id:12,code:'STK',name:'Tracked product'}]),'/inventory/locations/':page([{id:3,code:'MAIN',name:'Warehouse',is_active:true}]),
    '/inventory/position/':{quantity:'10'},'/accounting/accounts/tree/':[{id:8,code:'5100',name:'Stock cost corrections',account_type:'expense',is_active:true,is_postable:true,control:''}],
    'POST /inventory/adjustments/':{id:22,status:'posted'}});
  renderWithAuth(<InventoryApp section="overview" />);
  await userEvent.click(await screen.findByRole('button',{name:'Cost correction'}));
  await userEvent.selectOptions(screen.getByLabelText('Tracked item'),'12');
  await userEvent.selectOptions(screen.getByLabelText('Counted location'),'3');
  await userEvent.selectOptions(screen.getByLabelText('Original stock event'),original);
  await userEvent.type(screen.getByLabelText('Signed cost correction (+ increase / − decrease)'),'-50.25');
  await userEvent.selectOptions(screen.getByLabelText('Adjustment expense account'),'8');
  await userEvent.type(screen.getByLabelText('Reason and evidence reference'),'Documented acquisition impairment');
  await userEvent.click(screen.getByRole('button',{name:'Save'}));
  await waitFor(()=>expect(calls.find(c=>c.method==='POST'&&c.path==='/inventory/adjustments/')?.body).toMatchObject({quantity:'0',base_value:'-50.25',kind:'valuation',correction_of_id:original,expected_quantity:'10'}));
});


it('calculates a clearly identified margin scenario through the backend without changing saved prices',async()=>{
  const calls=mockApi({...common,'/catalog/items/12/':{id:12,code:'SCENARIO',name:'Scenario product',unit:'EA',currency:'BDT',unit_price:'100',is_active:true,profile:null},'/catalog/items/12/prices/':page([]),
    'POST /catalog/items/12/margin/':{date:'2026-10-21',currency:'BDT',sale:'100',cost:'75',margin:'25',percent:'25.000000',realized:false}});
  renderWithAuth(<CatalogApp section="pricing" id="12" />);
  await userEvent.click(await screen.findByRole('button',{name:'Margin scenario'}));
  await userEvent.type(screen.getByLabelText('Sales amount'),'100');await userEvent.type(screen.getByLabelText('Assumed cost'),'75');
  await userEvent.click(screen.getByRole('button',{name:'Calculate scenario'}));
  expect(await screen.findByText('Calculated scenario — not realized profit')).toBeVisible();
  expect(screen.getByText('BDT 25.00')).toBeVisible();
  expect(calls.find(c=>c.path==='/catalog/items/12/margin/')?.body).toMatchObject({sale:'100',cost:'75',currency:'BDT'});
  expect(calls.some(c=>c.method==='PATCH'||c.path.endsWith('/prices/')&&c.method==='POST')).toBe(false);
});
