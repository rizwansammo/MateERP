import { expect, test, type Page } from '@playwright/test';
import { apiPost, djangoShell, ensureUser, login, pngBuffer, savedPreference, strongPassword } from './support';

test.describe.configure({ mode: 'serial' });
let inventoryAccount: number, revenueAccount: number, cogsAccount: number;
let vendor: number, item: number, location: number, order: number;

async function post<T>(page:Page,path:string,data:unknown):Promise<T>{
  const response=await apiPost(page.request,page.context(),`/api/v1${path}`,data);
  expect(response.ok(),await response.text()).toBe(true);return response.json();
}

async function get<T>(page: Page, path: string): Promise<T> {
  const response = await page.request.get(`/api/v1${path}`);
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

test('catalog, procurement and receipt valuation persist through the real browser proxy', async ({ page }) => {
  test.setTimeout(120_000);
  const setup = JSON.parse(djangoShell(`
import json
from datetime import date
from types import SimpleNamespace
from django.conf import settings
assert settings.MATEERP_ENVIRONMENT == 'e2e'
from apps.accounts.models import User
from apps.company.models import CompanyProfile
from apps.company.services import create_company
from apps.accounting.models import Account, FiscalYear
from apps.accounting.services.setup import setup_chart, create_year, save_account
from apps.approvals.models import ApprovalPolicy
r=SimpleNamespace(user=User.objects.get(username='e2e-admin'),META={})
if not CompanyProfile.objects.exists(): create_company(r,{'display_name':'NetaMate','base_currency':'BDT','time_zone':'Asia/Dhaka','fiscal_year_start_month':1})
chart={a.code:a for a in Account.objects.all()} if Account.objects.exists() else {a.code:a for a in setup_chart(r)}
for code,purpose in [('2010','payable'),('1100','receivable')]:
    if not Account.objects.filter(control=purpose).exists(): save_account(r,{'control':purpose},chart[code].pk)
if not FiscalYear.objects.filter(start=date(2026,1,1)).exists(): create_year(r,date(2026,1,1))
for code,name,kind,purpose in [('E6INV','Inventory','asset','inventory'),('E6GRNI','GRNI','liability','grni')]:
    if not Account.objects.filter(control=purpose).exists(): save_account(r,{'code':code,'name':name,'account_type':kind,'control':purpose})
ApprovalPolicy.objects.filter(category='purchase_orders').update(is_required=False)
print(json.dumps({'inventory':Account.objects.get(control='inventory').pk,'revenue':chart['4100'].pk,'cogs':chart['5100'].pk}))
`)) as { inventory: number; revenue: number; cogs: number };
  inventoryAccount = setup.inventory; revenueAccount = setup.revenue; cogsAccount = setup.cogs;
  const supplier = await apiPost(page.request, page.context(), '/api/v1/purchasing/vendors/', { name: 'Phase 6 supplier', currency: 'BDT' });
  expect(supplier.ok(), await supplier.text()).toBe(true); vendor = (await supplier.json()).id;
  await page.goto('/catalog/products');
  await page.getByRole('button', { name: 'New unit', exact: true }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Code', { exact: true }).fill('E6EA');
  await dialog.getByLabel('Name', { exact: true }).fill('Each');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole('button', { name: 'New product', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('SKU / service code').fill('E6-WIDGET');
  await dialog.getByLabel('Name', { exact: true }).fill('Acceptance widget');
  await dialog.getByLabel('Classification', { exact: true }).selectOption('stock');
  const units = await get<{ results: { id: number; code: string }[] }>(page, '/catalog/units/');
  const unit = units.results.find(u => u.code === 'E6EA'); expect(unit).toBeTruthy();
  await dialog.getByLabel('Unit of measure').selectOption(String(unit!.id));
  await dialog.getByLabel('Fallback sales price').fill('100');
  await dialog.getByLabel('Revenue account', { exact: true }).selectOption(String(revenueAccount));
  await dialog.getByLabel('Cost of sales account', { exact: true }).selectOption(String(cogsAccount));
  await dialog.getByLabel('Inventory control account', { exact: true }).selectOption(String(inventoryAccount));
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(dialog).toBeHidden(); await expect(page.getByText('E6-WIDGET', { exact: true })).toBeVisible();
  item = (await get<{ results: { id: number }[] }>(page, '/catalog/items/?search=E6-WIDGET')).results[0]!.id;

  await page.goto('/inventory/locations');
  await page.getByRole('button', { name: 'New location', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Location code').fill('E6MAIN'); await dialog.getByLabel('Location name').fill('Acceptance warehouse');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toBeHidden();
  location = (await get<{ results: { id: number }[] }>(page, '/inventory/locations/?search=E6MAIN')).results[0]!.id;

  await page.goto('/purchases/orders');
  await page.getByRole('button', { name: 'New purchase order', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Vendor', { exact: true }).selectOption(String(vendor));
  await dialog.getByLabel('Order date').fill('2026-10-21');
  await dialog.getByLabel('Line 1 item').selectOption(String(item));
  await dialog.getByLabel('Line 1 quantity').fill('10');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toBeHidden();
  const orders = await get<{ results: { id: number; number: string }[] }>(page, '/purchasing/orders/');
  order = orders.results[0]!.id;
  await page.getByRole('link', { name: orders.results[0]!.number, exact: true }).click();
  await page.getByRole('button', { name: 'Submit for approval' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'submit', exact: true }).click();
  await page.getByRole('button', { name: 'Issue order' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'issue', exact: true }).click();
  await page.getByRole('button', { name: 'Receive / accept' }).click();
  dialog = page.getByRole('dialog');
  const detail = await get<{ lines: { id: number }[] }>(page, `/purchasing/orders/${order}/`);
  await dialog.getByLabel('Order line', { exact: true }).selectOption(String(detail.lines[0]!.id));
  await dialog.getByLabel('Acceptance date').fill('2026-10-21');
  await dialog.getByLabel('Accepted quantity', { exact: true }).fill('10');
  await dialog.getByLabel('Receiving location (tracked goods)').selectOption(String(location));
  await dialog.getByLabel('Delivery / acceptance reference').fill('E6-DELIVERY-1');
  await dialog.getByLabel('Inspection / acceptance notes').fill('Counted and accepted ten widgets');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toBeHidden();
  await page.goto('/inventory/valuation');
  await expect(page.getByText('E6-WIDGET', { exact: true })).toBeVisible();
  await expect(page.getByRole('row').filter({ hasText: 'E6-WIDGET' }).getByText(/1,000\.00/)).toBeVisible();
  const valuation = await get<{ reconciliation: { difference: string; stock_value: string } }>(page, '/inventory/valuation/');
  expect(valuation.reconciliation).toMatchObject({ difference: '0.000000', stock_value: '1000.000000' });
  await page.reload(); await expect(page.getByText('E6-WIDGET', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/phase6-inventory-light.png', fullPage: true });
});

test('receiving evidence uses validated private storage and browser downloads', async ({ page }) => {
  await page.goto(`/purchases/orders/${order}`);
  await page.getByRole('button', { name: 'Upload evidence', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Description / purpose').fill('Private supplier delivery note');
  await dialog.getByLabel('Document (PDF, PNG, JPEG or WEBP)').setInputFiles({ name: 'delivery.png', mimeType: 'image/png', buffer: pngBuffer() });
  await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toBeHidden();
  const link = page.getByRole('link', { name: 'delivery.png', exact: true }); await expect(link).toBeVisible();
  const response = await page.request.get((await link.getAttribute('href'))!);
  expect(response.status()).toBe(200); expect(response.headers()['cache-control']).toBe('private, no-store');
  expect((await response.body()).subarray(0, 4).toString('hex')).toBe('89504e47');
});

test('historical startup documentation is persistent and creates no corporate posting', async ({ page }) => {
  const count = () => djangoShell("from django.conf import settings; assert settings.MATEERP_ENVIRONMENT == 'e2e'; from apps.accounting.models import JournalEntry; print(JournalEntry.objects.count())");
  const before = count();
  await page.goto('/purchases/onboarding');
  await page.getByRole('button', { name: 'Document historical activity' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Unique original reference').fill('E6-HISTORY-STARTUP-1');
  await dialog.getByLabel('Original transaction date').fill('2026-01-05');
  await dialog.getByLabel('Original description').fill('Pre-registration startup hosting');
  await dialog.getByLabel('Original amount').fill('125.00');
  await dialog.getByLabel('Original payment source / outstanding obligation').fill('Documented pre-registration payment');
  await dialog.getByRole('checkbox', { name: 'Incurred before formal registration' }).check();
  await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toBeHidden();
  await expect(page.getByText('E6-HISTORY-STARTUP-1', { exact: true })).toBeVisible();
  await expect(page.getByText('Evidence only — no posting', { exact: true })).toBeVisible();
  await page.reload(); await expect(page.getByText('E6-HISTORY-STARTUP-1', { exact: true })).toBeVisible();
  expect(count()).toBe(before);
});

test('documented control transfer posts revenue and cost once through the order screen',async({page})=>{
  djangoShell(`
from django.conf import settings
assert settings.MATEERP_ENVIRONMENT=='e2e'
from types import SimpleNamespace
from apps.accounts.models import User
from apps.accounting.models import Account
from apps.accounting.services.setup import save_account
r=SimpleNamespace(user=User.objects.get(username='e2e-admin'),META={})
for code,purpose,kind in [('E6UNB','unbilled_revenue','asset'),('E6DEF','deferred_revenue','liability')]:
    if not Account.objects.filter(control=purpose).exists(): save_account(r,{'code':code,'name':purpose,'account_type':kind,'control':purpose})
`);
  const customer=await post<{id:number}>(page,'/sales/customers/',{name:'Phase 6 fulfillment customer',currency:'BDT'});
  const contract=await post<{id:number;lines:{id:number}[]}>(page,'/sales/orders/',{customer_id:customer.id,order_date:'2026-10-21',currency:'BDT',lines:[{item_id:item,description:'Accepted widgets',quantity:'2',unit_price:'200'}]});
  await post(page,`/sales/orders/${contract.id}/confirm/`,{});
  await page.goto(`/sales/orders/${contract.id}`);
  await page.getByRole('button',{name:'Document recognition policy',exact:true}).click();
  let dialog=page.getByRole('dialog');
  await dialog.getByLabel('Confirmed tracked product line').selectOption(String(contract.lines[0]!.id));
  await dialog.getByLabel('Contract / authorization reference').fill('E6-CONTROL-AGREEMENT');
  await dialog.getByLabel('Recognition condition and rationale').fill('Customer obtains control on documented acceptance; dispatch alone retains company ownership');
  await dialog.getByRole('button',{name:'Save contract policy'}).click();await expect(dialog).toBeHidden();
  await page.getByRole('button',{name:'Transfer control',exact:true}).click();dialog=page.getByRole('dialog');
  await dialog.getByLabel('Event date').fill('2026-10-21');await dialog.getByLabel('Quantity',{exact:true}).fill('2');
  await dialog.getByLabel('Source reference').fill('E6-ACCEPTANCE-1');await dialog.getByLabel('Evidence / acceptance reference').fill('Signed acceptance of two delivered widgets');
  await dialog.getByLabel('Stock location').selectOption(String(location));
  await dialog.getByRole('button',{name:'Record event'}).click();await expect(dialog).toBeHidden();
  await expect(page.getByText('E6-ACCEPTANCE-1',{exact:true})).toBeVisible();
  const controlled=await get<{results:{net_native:string;base_cogs:string}[]}>(page,`/billing/fulfillment/control-transfers/?order_id=${contract.id}`);
  expect(controlled.results[0]).toMatchObject({net_native:'400.000000',base_cogs:'200.000000'});
  const value=await get<{reconciliation:{stock_value:string;difference:string}}>(page,'/inventory/valuation/');
  expect(value.reconciliation).toMatchObject({stock_value:'800.000000',difference:'0.000000'});
  await page.reload();await expect(page.getByText('E6-ACCEPTANCE-1',{exact:true})).toBeVisible();
});

test('capitalization and manual depreciation retain their real acquisition and posting',async({page})=>{
  djangoShell(`
from django.conf import settings
assert settings.MATEERP_ENVIRONMENT=='e2e'
from types import SimpleNamespace
from apps.accounts.models import User
from apps.accounting.models import Account
from apps.accounting.services.setup import save_account
from apps.approvals.models import ApprovalPolicy
r=SimpleNamespace(user=User.objects.get(username='e2e-admin'),META={})
for code,purpose in [('E6FA','fixed_assets'),('E6AD','accumulated_depreciation')]:
    if not Account.objects.filter(control=purpose).exists(): save_account(r,{'code':code,'name':purpose,'account_type':'asset','control':purpose})
ApprovalPolicy.objects.filter(category='financial_adjustments').update(is_required=False)
`);
  const accounts=await get<{id:number;code:string}[]>(page,'/accounting/accounts/tree/');
  const expense=accounts.find(a=>a.code==='6100')!.id;
  const bill=await post<{id:number}>(page,'/purchasing/bills/',{vendor_id:vendor,vendor_reference:'E6-SERVER-ACQ',bill_date:'2026-01-01',due_date:'2026-01-01',currency:'BDT',lines:[{description:'E6 server acquisition',quantity:'1',unit_price:'60000',account_id:expense}]});
  await post(page,`/purchasing/bills/${bill.id}/post/`,{});
  const sources=await get<{results:{id:number}[]}>(page,'/assets/acquisitions/?search=E6-SERVER-ACQ');
  expect(sources.results.length).toBe(1);
  await page.goto('/assets/register');await page.getByRole('button',{name:'Capitalize asset',exact:true}).click();
  let dialog=page.getByRole('dialog');await dialog.getByLabel('Unique asset tag').fill('E6-SERVER');
  await dialog.getByLabel('Asset name').fill('Acceptance server');await dialog.getByLabel('Category',{exact:true}).fill('Computers');
  await dialog.getByLabel('Posted acquisition source').selectOption(String(sources.results[0]!.id));
  await dialog.getByLabel('Historical cost claimed (company base currency)').fill('60000');
  await dialog.getByLabel('Capitalization recognition date').fill('2026-01-01');await dialog.getByLabel('Available for use').fill('2026-01-01');
  await dialog.getByLabel('Depreciation expense account').selectOption(String(expense));
  await dialog.getByLabel('Capitalization authority / reclassification evidence').fill('Reviewed source reclassification: no duplicate purchase or liability');
  await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toBeHidden();
  await page.getByRole('link',{name:'E6-SERVER',exact:true}).click();
  await page.getByRole('button',{name:'Post next depreciation',exact:true}).click();dialog=page.getByRole('dialog');
  await dialog.getByLabel('Posting basis / delayed recognition reason').fill('January service month verified');
  await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toBeHidden();
  const assets=await get<{results:{id:string;accumulated:string;book_value:string}[]}>(page,'/assets/register/?search=E6-SERVER');
  expect(assets.results[0]).toMatchObject({accumulated:'1000.000000',book_value:'59000.000000'});
  await page.reload();await expect(page.getByRole('heading',{name:'E6-SERVER — Acceptance server',exact:true})).toBeVisible();
  const reconciliation=await get<{cost_difference:string;depreciation_difference:string}>(page,'/assets/register/reconciliation/');
  expect(reconciliation).toMatchObject({cost_difference:'0.000000',depreciation_difference:'0.000000'});
});

test('approved budget compares tagged posted costs and survives browser refresh',async({page,browser})=>{
  const accounts=await get<{id:number;code:string}[]>(page,'/accounting/accounts/tree/');const expense=accounts.find(a=>a.code==='6100')!.id;
  const bill=await post<{id:number}>(page,'/purchasing/bills/',{vendor_id:vendor,vendor_reference:'E6-BUDGET-HOST',bill_date:'2026-10-21',due_date:'2026-10-21',currency:'BDT',lines:[{description:'E6 hosting cost',quantity:'1',unit_price:'1000',account_id:expense}]});
  await post(page,`/purchasing/bills/${bill.id}/post/`,{});
  await page.goto('/budgets/costcenters');await page.getByRole('button',{name:'New cost center',exact:true}).click();let dialog=page.getByRole('dialog');
  await dialog.getByLabel('Code',{exact:true}).fill('E6HOST');await dialog.getByLabel('Name',{exact:true}).fill('Hosting infrastructure');
  await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toBeHidden();
  const center=(await get<{results:{id:number}[]}>(page,'/budgeting/cost-centers/?search=E6HOST')).results[0]!.id;
  await page.goto(`/purchases/bills/${bill.id}`);await page.getByRole('button',{name:'Classify spending',exact:true}).click();dialog=page.getByRole('dialog');
  await dialog.getByLabel('Cost center',{exact:true}).selectOption(String(center));await dialog.getByLabel('Classification authority and rationale').fill('Hosting source evidence reviewed');
  await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toBeHidden();
  await page.goto('/budgets/budgets');await page.getByRole('button',{name:'New budget',exact:true}).click();dialog=page.getByRole('dialog');
  await dialog.getByLabel('Budget name').fill('E6 Hosting plan');const years=await get<{results:{id:number;start:string;end:string}[]}>(page,'/accounting/fiscal-years/');
  const fiscal=years.results.find(y=>y.start<='2026-10-01'&&y.end>='2026-10-31');expect(fiscal).toBeTruthy();
  await dialog.getByLabel('Fiscal year',{exact:true}).selectOption(String(fiscal!.id));
  await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toBeHidden();
  await page.getByRole('link',{name:'E6 Hosting plan',exact:true}).click();await page.getByRole('button',{name:'New revision',exact:true}).click();dialog=page.getByRole('dialog');
  await dialog.getByLabel('Revision purpose and authority').fill('Reviewed monthly hosting plan');await dialog.getByLabel('Line 1 month').fill('2026-10');
  await dialog.getByLabel('Line 1 account').selectOption(String(expense));await dialog.getByLabel('Line 1 cost center').selectOption(String(center));
  await dialog.getByLabel('Line 1 budget amount').fill('1500');await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toBeHidden();
  await page.getByRole('button',{name:'Submit revision for approval'}).click();
  const submission=page.getByRole('dialog');await submission.getByRole('button',{name:'Submit for approval',exact:true}).click();await expect(submission).toBeHidden();
  const budgets=await get<{results:{id:number}[]}>(page,'/budgeting/budgets/?search=E6%20Hosting');
  const revisions=await get<{results:{id:number;status:string;approval_id:number|null}[]}>(page,`/budgeting/revisions/?budget_id=${budgets.results[0]!.id}`);
  const revision=revisions.results[0]!;
  expect(revision.status).toBe('pending');expect(revision.approval_id).toBeTruthy();
  const self=await apiPost(page.request,page.context(),`/api/v1/approvals/requests/${revision.approval_id}/approve/`,{reason:'Self approval is rejected'});
  expect(self.status()).toBe(403);
  const password=strongPassword();ensureUser('e2e-phase6-reviewer','administrator',password);
  const context=await browser.newContext({storageState:{cookies:[],origins:[]}});const reviewer=await context.newPage();
  await login(reviewer,'e2e-phase6-reviewer',password);await expect(reviewer).toHaveURL(/dashboard/);
  const approval=await apiPost(reviewer.request,context,`/api/v1/approvals/requests/${revision.approval_id}/approve/`,{reason:'Independent budget scope and evidence reviewed'});
  expect(approval.ok(),await approval.text()).toBe(true);await context.close();
  await page.reload();await expect(page.getByText('Original vs revised vs posted actual — v1',{exact:true})).toBeVisible();
  const comparisons=await get<{actual:string;remaining:string}[]>(page,`/budgeting/revisions/${revision.id}/comparison/`);
  expect(comparisons[0]).toMatchObject({actual:'1000.000000',remaining:'500.000000'});
});


test('executive reports show real posted activity, backend filters and safe exports',async({page})=>{
  await page.goto('/dashboard');
  await page.getByLabel('Dashboard period').selectOption('custom');
  await page.getByLabel('Dashboard from').fill('2026-01-01');await page.getByLabel('Dashboard to').fill('2026-10-31');
  await expect(page.getByText('Revenue (accrual)',{exact:true})).toBeVisible();
  await expect(page.getByText('Revenue vs expenses',{exact:true})).toBeVisible();
  const result=await get<{from:string;to:string;metrics:{key:string;value:string}[]}>(page,'/reporting/dashboard/?range=custom&from=2026-01-01&to=2026-10-31');
  expect(result.from).toBe('2026-01-01');expect(result.to).toBe('2026-10-31');
  const ledgerRevenue=djangoShell(`
from django.conf import settings
assert settings.MATEERP_ENVIRONMENT=='e2e'
from decimal import Decimal
from django.db.models import Sum
from apps.accounting.models import JournalLine
totals=JournalLine.objects.filter(journal__status='posted',journal__posting_date__range=('2026-01-01','2026-10-31'),account__account_type='revenue').aggregate(credit=Sum('base_credit'),debit=Sum('base_debit'))
print(format((totals['credit'] or Decimal(0))-(totals['debit'] or Decimal(0)),'.6f'))
`);
  expect(result.metrics.find(m=>m.key==='revenue')?.value).toBe(ledgerRevenue);
  await page.goto('/reports');await expect(page.getByRole('heading',{name:'Reports & Analytics',exact:true})).toBeVisible();
  await page.getByRole('link',{name:/Invoicing by Customer/}).click();
  await expect(page.getByLabel('Filter customer')).toBeVisible();
  const customer=await get<{results:{id:number}[]}>(page,'/sales/customers/?search=Phase%206%20fulfillment');
  await page.getByLabel('Filter customer').selectOption(String(customer.results[0]!.id));
  const href=await page.getByRole('link',{name:'Export CSV',exact:true}).getAttribute('href');
  expect(href).toContain(`customer_id=${customer.results[0]!.id}`);
  const exported=await page.request.get(href!);expect(exported.ok()).toBe(true);expect(exported.headers()['content-type']).toContain('text/csv');
  await page.goto('/reports/cash-flow');await expect(page.getByRole('heading',{name:'Cash Flow',exact:true})).toBeVisible();
});


test('supplier cancellation and retained valuation correction keep both controls reconciled',async({page})=>{
  await page.goto(`/purchases/orders/${order}`);await page.getByRole('button',{name:'Return goods',exact:true}).click();
  let dialog=page.getByRole('dialog');await dialog.getByLabel('Return date').fill('2026-10-21');
  await dialog.getByLabel('Accepted return quantity').fill('1');await dialog.getByLabel('Return from location').selectOption(String(location));
  await dialog.getByLabel('Purchase-return cost variance account').selectOption(String(cogsAccount));
  await dialog.getByLabel('Supplier acceptance / cancellation reference').fill('E6-SUPPLIER-CANCEL');
  await dialog.getByLabel('Supplier agreement and settlement treatment').fill('Supplier accepts unmatched cancellation; no AP or cash refund');
  await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toBeHidden();
  const receiving=await get<{difference:string}>(page,'/purchasing/receipts/reconciliation/');expect(receiving.difference).toBe('0.000000');
  await page.goto('/inventory/overview');await page.getByRole('button',{name:'Cost correction',exact:true}).click();dialog=page.getByRole('dialog');
  await dialog.getByLabel('Tracked item').selectOption(String(item));await dialog.getByLabel('Counted location').selectOption(String(location));
  const moves=await get<{results:{id:string;kind:string}[]}>(page,`/inventory/movements/?item_id=${item}`);const original=moves.results.find(m=>m.kind==='receipt')!;
  await dialog.getByLabel('Original stock event').selectOption(original.id);await dialog.getByLabel('Movement date').fill('2026-10-21');
  await dialog.getByLabel('Signed cost correction (+ increase / − decrease)').fill('-50');await dialog.getByLabel('Adjustment expense account').selectOption(String(cogsAccount));
  await dialog.getByLabel('Reason and evidence reference').fill('Documented impairment of retained goods, original acquisition reference retained');
  await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toBeHidden();
  const valuation=await get<{reconciliation:{difference:string;stock_value:string}}>(page,'/inventory/valuation/');
  expect(valuation.reconciliation).toMatchObject({difference:'0.000000',stock_value:'650.000000'});
  await expect(page.getByRole('row').filter({has:page.getByRole('link',{name:'E6-WIDGET',exact:true})})).toContainText('92.857143');
});

test('an unused capitalization can be corrected with a retained reversal and released source',async({page})=>{
  const accounts=await get<{id:number;code:string}[]>(page,'/accounting/accounts/tree/');const expense=accounts.find(a=>a.code==='6100')!.id;
  const bill=await post<{id:number}>(page,'/purchasing/bills/',{vendor_id:vendor,vendor_reference:'E6-REVERSE-ACQ',bill_date:'2026-10-21',due_date:'2026-10-21',currency:'BDT',lines:[{description:'Unused capitalization correction',quantity:'1',unit_price:'500',account_id:expense}]});
  await post(page,`/purchasing/bills/${bill.id}/post/`,{});
  const source=(await get<{results:{id:number}[]}>(page,'/assets/acquisitions/?search=E6-REVERSE-ACQ')).results[0]!.id;
  const action=await post<{result_id:string}>(page,'/assets/register/',{source_line_id:source,tag:'E6-CANCELLED',name:'Unused registration',category:'Equipment',cost:'500',residual:'0',useful_life_months:60,depreciation_account_id:expense,recognition_date:'2026-10-21',in_service_date:'2026-10-21',reason:'Acquisition source verified',key:'e6-capitalize-before-correction'});
  await page.goto(`/assets/register/${action.result_id}`);await page.getByRole('button',{name:'Reverse capitalization',exact:true}).click();const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Permitted reversal date').fill('2026-10-21');await dialog.getByLabel('Correction authority and rationale').fill('Unused registration error corrected with full original history');
  await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toBeHidden();
  await expect(page.getByRole('link',{name:'Reversal journal',exact:true})).toBeVisible();
  const available=(await get<{results:{available_base:string}[]}>(page,'/assets/acquisitions/?search=E6-REVERSE-ACQ')).results[0]!;
  expect(available.available_base).toBe('500.000000');
});

test('Phase 6 shell retains approved geometry in light, dark, compact and mobile states',async({page,browser})=>{
  await page.setViewportSize({width:1440,height:900});await page.goto('/inventory/overview');
  const sidebar=page.getByTestId('sidebar');expect(await sidebar.evaluate(e=>e.getBoundingClientRect().width)).toBe(264);
  await expect(page.getByText('Phase 6 · Operations & reporting',{exact:true})).toBeVisible();
  await expect(page.getByRole('banner')).toHaveCSS('height','56px');await expect(sidebar).toHaveCSS('background-color','rgb(10, 15, 22)');
  await expect(page.getByRole('row').filter({has:page.getByRole('link',{name:'E6-WIDGET',exact:true})})).toContainText('92.857143');
  await expect(page.getByText('Stock value by item',{exact:true})).toBeVisible();
  await page.screenshot({path:'test-results/phase6-inventory-light.png',fullPage:true});
  await savedPreference(page,()=>page.getByRole('button',{name:'Switch to dark mode'}).click());await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.screenshot({path:'test-results/phase6-inventory-dark.png',fullPage:true});
  await savedPreference(page,()=>page.getByRole('button',{name:'Collapse sidebar'}).click());await expect.poll(()=>sidebar.evaluate(e=>e.getBoundingClientRect().width)).toBe(64);
  await page.screenshot({path:'test-results/phase6-inventory-compact.png',fullPage:true});
  await savedPreference(page,()=>page.getByRole('button',{name:'Expand sidebar'}).click());await savedPreference(page,()=>page.getByRole('button',{name:'Switch to light mode'}).click());
  await page.setViewportSize({width:820,height:900});await expect(sidebar).not.toBeInViewport();await page.getByRole('button',{name:'Open navigation'}).click();await expect(sidebar).toBeInViewport();
  await page.keyboard.press('Escape');await expect(sidebar).not.toBeInViewport();await page.screenshot({path:'test-results/phase6-inventory-mobile.png',fullPage:true});
  const referenceUrl=process.env.MATEERP_PROTOTYPE_URL;
  if(referenceUrl){
    const context=await browser.newContext({viewport:{width:1440,height:900}});const reference=await context.newPage();
    await reference.goto(`${referenceUrl}/inventory/overview`);await expect(reference.getByText('Inventory Overview',{exact:true}).first()).toBeVisible();
    await reference.screenshot({path:'test-results/phase6-prototype-inventory-light.png',fullPage:true});await context.close();
  }
});
