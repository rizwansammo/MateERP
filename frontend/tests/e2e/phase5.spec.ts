import { expect, test, type Page } from '@playwright/test';
import { apiPost, csrfHeaders, djangoShell, ensureUser, login, pngBuffer, strongPassword } from './support';

test.describe.configure({ mode: 'serial' });
let a:number, b:number, external:number, bank:number, expenseAccount:number, contribution:number;
let reviewerPassword:string, governorPassword:string;

async function get<T>(page:Page,path:string):Promise<T> {
  const response=await page.request.get(`/api/v1${path}`);
  expect(response.ok(),await response.text()).toBe(true); return response.json();
}
async function post<T>(page:Page,path:string,data:unknown={}):Promise<T> {
  const response=await apiPost(page.request,page.context(),`/api/v1${path}`,data);
  expect(response.ok(),await response.text()).toBe(true); return response.json();
}

test('founder participants and actual funding use the application and independent verification',async({page,browser})=>{
  test.setTimeout(120000);
  reviewerPassword=strongPassword(); governorPassword=strongPassword();
  const reviewerId=ensureUser('e2e-phase5-reviewer','administrator',reviewerPassword);
  ensureUser('e2e-phase5-governor','administrator',governorPassword);
  const setup=JSON.parse(djangoShell(`
import json
from datetime import date
from types import SimpleNamespace
from django.conf import settings
assert settings.MATEERP_ENVIRONMENT == 'e2e'
from apps.accounts.models import User
from apps.company.models import CompanyProfile, ModuleSetting
from apps.company.services import create_company
from apps.accounting.models import Account, FiscalYear
from apps.accounting.services.setup import setup_chart, save_account, create_year
from apps.banking.services import save_account as save_bank
from apps.approvals.models import ApprovalPolicy
r=SimpleNamespace(user=User.objects.get(username='e2e-admin'),META={})
if not CompanyProfile.objects.exists(): create_company(r,{'display_name':'NetaMate','base_currency':'BDT','time_zone':'Asia/Dhaka','fiscal_year_start_month':1})
chart={a.code:a for a in Account.objects.all()} if Account.objects.exists() else {a.code:a for a in setup_chart(r)}
if not FiscalYear.objects.filter(start=date(2027,1,1)).exists(): create_year(r,date(2027,1,1))
for index,purpose in enumerate(['founder_payable','founder_loan','founder_pending','founder_equity','share_capital','share_premium']):
    if not Account.objects.filter(control=purpose).exists(): save_account(r,{'code':'E5'+str(index),'name':purpose,'account_type':'liability' if index<3 else 'equity','control':purpose})
gl=save_account(r,{'code':'E5BANK','name':'Phase 5 acceptance bank','account_type':'asset','currency':'BDT'})
bank=save_bank(r,{'name':'Phase 5 acceptance bank','kind':'bank','currency':'BDT','gl_account_id':gl.pk})
for key in ['founder','ownership']: ModuleSetting.objects.update_or_create(key=key,defaults={'enabled':True})
ApprovalPolicy.objects.filter(category__in=['financial_adjustments','admin_changes']).update(is_required=False)
ApprovalPolicy.objects.filter(category='ownership_changes').update(is_required=True,allow_self_approval=False,required_approvals=1,approver_role=None)
print(json.dumps({'bank':bank.pk,'expense':chart['6100'].pk}))
`)) as {bank:number;expense:number};
  bank=setup.bank; expenseAccount=setup.expense;
  await page.goto('/ownership/shareholders'); await page.getByRole('button',{name:'Add participant'}).click();
  let dialog=page.getByRole('dialog');
  await dialog.getByLabel('Full / organization name').fill('Phase 5 Founder A');
  await dialog.getByLabel('Participation starts').fill('2026-01-01');
  const current=await get<{id:number}>(page,'/auth/me/');
  await dialog.getByLabel('Linked ERP user ID (optional)').fill(String(current.id));
  await dialog.getByRole('checkbox',{name:'Shareholder / investor'}).check();
  await dialog.getByRole('button',{name:'Save',exact:true}).click(); await expect(dialog).toHaveCount(0);
  const parties=await get<{results:{id:number;name:string}[]}>(page,'/founders/parties/');
  a=parties.results.find(p=>p.name==='Phase 5 Founder A')!.id;
  b=(await post<{id:number}>(page,'/founders/parties/',{name:'Phase 5 Founder B',kind:'individual',joined:'2026-01-01',is_founder:true,is_shareholder:true,user_id:reviewerId})).id;
  external=(await post<{id:number}>(page,'/founders/parties/',{name:'Phase 5 External Partner',kind:'individual',joined:'2026-01-01',is_founder:true,is_shareholder:true})).id;
  await page.goto('/founder/contributions'); await page.getByRole('button',{name:'Company receipt',exact:true}).click();
  dialog=page.getByRole('dialog'); await dialog.getByLabel('Founder / shareholder').selectOption(String(a));
  await dialog.getByLabel('Business date').fill('2027-01-10'); await dialog.getByLabel('Currency',{exact:true}).selectOption('BDT');
  await dialog.getByLabel('Amount',{exact:true}).fill('20000');
  await dialog.getByLabel('Company bank / cash account').selectOption(String(bank));
  await dialog.getByLabel('Payment / agreement reference').fill('PH5-RECEIPT-1');
  await dialog.getByRole('button',{name:'Save',exact:true}).click(); await expect(dialog).toHaveCount(0);
  const receipts=await get<{results:{id:number;reference:string;journal:number|null}[]}>(page,'/founders/transactions/?kind=receipt');
  contribution=receipts.results.find(p=>p.reference==='PH5-RECEIPT-1')!.id;
  expect(receipts.results.find(p=>p.id===contribution)!.journal).toBeNull();
  const self=await apiPost(page.request,page.context(),`/api/v1/founders/transactions/${contribution}/verify/`,{}); expect(self.status()).toBe(403);
  const context=await browser.newContext({storageState:{cookies:[],origins:[]}}); const verifier=await context.newPage();
  await login(verifier,'e2e-phase5-reviewer',reviewerPassword); await expect(verifier).toHaveURL(/dashboard/);
  await verifier.goto(`/founder/contributions/${contribution}`);
  await verifier.getByRole('button',{name:'Preview accounting'}).click(); await verifier.getByRole('checkbox').check();
  await verifier.getByRole('button',{name:'Verify transaction',exact:true}).click();
  await expect(verifier.getByText('Posted',{exact:true})).toBeVisible();
  await context.close(); await page.reload();
  expect((await get<{status:string}>(page,`/founders/transactions/${contribution}/`)).status).toBe('posted');
  const noCsrf=await page.request.post('/api/v1/founders/parties/',{data:{name:'Unauthorized'},headers:{Origin:'http://localhost:3100'}}); expect(noCsrf.status()).toBe(403);
});

test('personal confirmations leave the company liability intact and block duplicate reimbursement',async({page,browser})=>{
  const expense=await post<{id:number;expense:number}>(page,'/founders/transactions/',{kind:'expense',classification:'payable',party_id:a,date:'2027-01-11',currency:'BDT',expense:{description:'Phase 5 founder-paid cost',account_id:expenseAccount,amount:'20000'},client_key:'e2e-phase5-expense'});
  const context=await browser.newContext({storageState:{cookies:[],origins:[]}}); const verifier=await context.newPage();
  await login(verifier,'e2e-phase5-reviewer',reviewerPassword); await expect(verifier).toHaveURL(/dashboard/);
  await post(verifier,`/founders/transactions/${expense.id}/verify/`);
  const policy=await post<{id:number}>(page,'/founders/policies/',{name:'Phase 5 equal sharing',basis:'equal',effective_from:'2027-01-01',weights:{[a]:'1',[b]:'1'}});
  await post(page,`/founders/policies/${policy.id}/activate/`);
  await post(page,'/founders/sharing/',{expense_id:expense.expense});
  const balances=await get<{results:{id:number;amount:string}[]}>(page,'/founders/personal-balances/');
  const obligation=balances.results[0]!;
  const settlement=await post<{id:number}>(page,'/founders/settlements/',{payer_id:b,recipient_id:a,date:'2027-01-12',currency:'BDT',amount:'10000',allocations:[{obligation_id:obligation.id,amount:'10000'}],client_key:'e2e-phase5-personal'});
  await post(verifier,`/founders/settlements/${settlement.id}/confirm/`,{party_id:b,mode:'authenticated',reference:'Personal transfer sent'});
  await page.goto(`/founder/settlements/${settlement.id}`); await page.getByRole('button',{name:/confirm/i}).first().click();
  const dialog=page.getByRole('dialog'); await dialog.getByLabel(/participant/i).selectOption(String(a)); await dialog.getByLabel('Receipt / authority reference').fill('Received personally');
  await dialog.getByRole('button',{name:'Save',exact:true}).click(); await expect(dialog).toHaveCount(0);
  const obligations=await get<{results:{id:number;origin_id:number;outstanding:string}[]}>(page,'/founders/obligations/');
  const corporate=obligations.results.find(o=>o.origin_id===expense.id)!; expect(corporate.outstanding).toMatch(/^20000(?:\.0+)?$/);
  const blocked=await apiPost(page.request,page.context(),'/api/v1/founders/transactions/',{kind:'reimbursement',classification:'payable',party_id:a,date:'2027-01-13',currency:'BDT',amount:'20000',bank_id:bank,allocations:[{obligation_id:corporate.id,amount:'20000'}],client_key:'e2e-phase5-blocked'});
  expect(blocked.ok()).toBe(false); expect((await blocked.json()).error.code).toBe('duplicate_recovery_blocked');
  await context.close();
});

test('provisional 50:50 can become 40:40:20 with consent, external evidence and independent review',async({page,browser})=>{
  test.setTimeout(120000);
  const contexts=[];
  const reviewerContext=await browser.newContext({storageState:{cookies:[],origins:[]}}); contexts.push(reviewerContext);
  const reviewer=await reviewerContext.newPage(); await login(reviewer,'e2e-phase5-reviewer',reviewerPassword); await expect(reviewer).toHaveURL(/dashboard/);
  const governorContext=await browser.newContext({storageState:{cookies:[],origins:[]}}); contexts.push(governorContext);
  const governor=await governorContext.newPage(); await login(governor,'e2e-phase5-governor',governorPassword); await expect(governor).toHaveURL(/dashboard/);
  for(const [index,weights] of [{[a]:'50',[b]:'50'},{[a]:'40',[b]:'40',[external]:'20'}].entries()){
    const proposal=await post<{id:number}>(page,'/ownership/proposals/',{kind:'provisional',title:index?'New partner amendment':'Original agreement',effective_date:index?'2026-03-01':'2026-01-01',rationale:'All affected parties authorize',legal_reference:`E2E-AGREEMENT-${index}`,weights,client_key:`e2e-phase5-agreement-${index}`});
    for(const party of Object.keys(weights)){
      const response=await page.request.post('/api/v1/founders/evidence/',{headers:await csrfHeaders(page.context()),multipart:{proposal_id:String(proposal.id),party_id:party,title:'Signed participant authorization',file:{name:'authorization.png',mimeType:'image/png',buffer:pngBuffer()}}});
      expect(response.ok(),await response.text()).toBe(true);
    }
    const impersonate=await apiPost(page.request,page.context(),`/api/v1/ownership/proposals/${proposal.id}/consent/`,{party_id:b,mode:'authenticated',reference:'Cannot act as B'}); expect(impersonate.status()).toBe(403);
    await post(page,`/ownership/proposals/${proposal.id}/consent/`,{party_id:a,mode:'authenticated',reference:'A agrees'});
    await post(reviewer,`/ownership/proposals/${proposal.id}/consent/`,{party_id:b,mode:'authenticated',reference:'B agrees'});
    if(index) await post(page,`/ownership/proposals/${proposal.id}/consent/`,{party_id:external,mode:'attestation',reference:'Authorized signed external-party evidence, recorded by operator'});
    const pending=await post<{approval:number}>(page,`/ownership/proposals/${proposal.id}/submit/`);
    await post(governor,`/approvals/requests/${pending.approval}/approve/`,{reason:'Independent evidence review'});
    await page.goto(`/ownership/history/${proposal.id}`); await page.getByRole('button',{name:'Confirm documented effect'}).click();
    await expect(page.getByText('Confirmed',{exact:true})).toBeVisible();
  }
  const register=await get<{provisional:{weights:Record<string,string>};formal:Record<string,unknown>}>(page,'/ownership/register/?date=2026-04-01');
  expect(register.provisional.weights).toEqual({[a]:'40',[b]:'40',[external]:'20'}); expect(register.formal).toEqual({});
  for(const context of contexts) await context.close();
});

test('planner persists actual recurrence-derived forecasts without creating accounting events',async({page})=>{
  const vendor=await post<{id:number}>(page,'/purchasing/vendors/',{name:'Phase 5 forecast vendor',currency:'BDT'});
  for(const [name,amount] of [['VPS','4000'],['Subscription','2000']]) await post(page,'/purchasing/recurring/',{name:`Phase 5 ${name}`,vendor_id:vendor.id,currency:'BDT',frequency:'monthly',interval:1,start_date:'2027-01-01',description:name,account_id:expenseAccount,amount,payment_mode:'accrued'});
  await page.goto('/founder/sharing'); await page.getByRole('radio',{name:'12-month Forecast',exact:true}).click();
  await page.getByRole('button',{name:'Choose cost sources'}).click();
  await page.getByRole('checkbox',{name:'Include all recurring schedules'}).uncheck();
  await page.getByRole('checkbox',{name:'Phase 5 VPS',exact:true}).check();
  await page.getByRole('checkbox',{name:'Phase 5 Subscription',exact:true}).check();
  await page.getByLabel('Starts').fill('2027-01-01'); await page.getByLabel('Snapshot name').fill('Phase 5 annual plan');
  await page.getByRole('button',{name:'Save immutable forecast'}).click(); await expect(page.getByText(/Saved forecast #/)).toBeVisible();
  await expect(page.getByRole('table').first()).toContainText('6,000.00'); await page.reload();
  await page.getByRole('radio',{name:'12-month Forecast',exact:true}).click(); await expect(page.getByText('Phase 5 annual plan',{exact:true})).toBeVisible();
  const overview=await get<{reconciliation:{difference:string}[]}>(page,'/founders/overview/');
  expect(overview.reconciliation.every(r=>/^0(?:\.0+)?$/.test(r.difference))).toBe(true);
});

test('documented formal issuance dilutes units without inventing cash or changing provisional agreements',async({page,browser})=>{
  test.setTimeout(120000);
  const shareClass=await post<{id:number}>(page,'/ownership/classes/',{name:'Phase 5 ordinary shares',currency:'BDT',par_value:'100',rights:'Documented equal economic rights'});
  const reviewerContext=await browser.newContext({storageState:{cookies:[],origins:[]}});
  const reviewer=await reviewerContext.newPage(); await login(reviewer,'e2e-phase5-reviewer',reviewerPassword); await expect(reviewer).toHaveURL(/dashboard/);
  const governorContext=await browser.newContext({storageState:{cookies:[],origins:[]}});
  const governor=await governorContext.newPage(); await login(governor,'e2e-phase5-governor',governorPassword); await expect(governor).toHaveURL(/dashboard/);
  for(const [index,definition] of [
    {kind:'opening',lines:[{recipient_id:a,units:'5000',price:'100'},{recipient_id:b,units:'5000',price:'100'}]},
    {kind:'issuance',lines:[{recipient_id:external,units:'2500',price:'120'}]},
  ].entries()){
    const proposal=await post<{id:number;snapshot:{required_parties:number[]}}>(page,'/ownership/proposals/',{...definition,title:`Documented formal event ${index}`,effective_date:index?'2026-04-01':'2026-01-01',share_class_id:shareClass.id,rationale:'Evidence-backed register event',legal_reference:`E2E-FORMAL-${index}`,client_key:`e2e-phase5-formal-${index}`});
    for(const party of proposal.snapshot.required_parties){
      const response=await page.request.post('/api/v1/founders/evidence/',{headers:await csrfHeaders(page.context()),multipart:{proposal_id:String(proposal.id),party_id:String(party),title:'Formal authorization',file:{name:'signed-evidence.png',mimeType:'image/png',buffer:pngBuffer()}}}); expect(response.ok(),await response.text()).toBe(true);
    }
    for(const party of proposal.snapshot.required_parties) await post(party===b?reviewer:page,`/ownership/proposals/${proposal.id}/consent/`,{party_id:party,mode:party===external?'attestation':'authenticated',reference:'Documented authorization by the affected party'});
    const pending=await post<{approval:number}>(page,`/ownership/proposals/${proposal.id}/submit/`);
    await post(governor,`/approvals/requests/${pending.approval}/approve/`,{reason:'Independent formal-document review'});
    await post(page,`/ownership/proposals/${proposal.id}/confirm/`);
  }
  const register=await get<{formal:Record<string,{total:string;units:Record<string,string>}>}>(page,'/ownership/register/');
  expect(register.formal[String(shareClass.id)]).toMatchObject({total:'12500',units:{[a]:'5000',[b]:'5000',[external]:'2500'}});
  const capital=await get<{classes:{id:number;paid_in:string;unpaid_commitments:string}[]}>(page,'/ownership/capital/');
  const record=capital.classes.find(c=>c.id===shareClass.id)!; expect(record.paid_in).toMatch(/^0(?:\.0+)?$/); expect(record.unpaid_commitments).toMatch(/^1300000(?:\.0+)?$/);
  // The screen loads its dated capital projection after navigation. Wait for
  // that response rather than racing the existing loading state on busy hosts.
  const capitalLoaded=page.waitForResponse(r=>r.url().includes('/api/v1/ownership/capital/')&&r.request().method()==='GET');
  await page.goto('/ownership/capital');const capitalResponse=await capitalLoaded;
  expect(capitalResponse.ok(),await capitalResponse.text()).toBe(true);
  await expect(page.getByText('12500',{exact:true})).toBeVisible();
  await reviewerContext.close(); await governorContext.close();
});

test('consumed annual reserves roll only unused surplus forward and release it without another cash posting',async({page})=>{
  const vendor=await post<{id:number}>(page,'/purchasing/vendors/',{name:'Phase 5 annual provider',currency:'BDT'});
  const schedule=await post<{id:number}>(page,'/purchasing/recurring/',{name:'Phase 5 annual renewal',vendor_id:vendor.id,currency:'BDT',frequency:'yearly',interval:1,start_date:'2027-12-01',description:'Discounted annual renewal',account_id:expenseAccount,amount:'800',payment_mode:'paid',bank_account_id:bank});
  const original=await post<{id:number}>(page,'/founders/reserves/',{name:'Phase 5 original cycle',schedule_id:schedule.id,starts:'2027-01-01',renewal:'2027-12-01',target:'1200'});
  const funding=await post<{id:number}>(page,'/founders/designations/',{receipt_id:contribution,reserve_id:original.id,month:'2027-01-01',amount:'1200'});
  await post(page,'/purchasing/recurring/run/',{until:'2027-12-01',schedule_ids:[schedule.id]});
  const generated=await get<{runs:{expense_id:number}[]}>(page,`/purchasing/recurring/${schedule.id}/`);
  const expense=generated.runs[0]!.expense_id; await post(page,`/purchasing/expenses/${expense}/post/`);
  await post(page,`/founders/designations/${funding.id}/consume/`,{expense_id:expense,amount:'800'});
  const before=await get<{count:number}>(page,'/accounting/journals/?page_size=1');
  await page.goto('/founder/sharing'); await page.getByRole('radio',{name:'Annual Reserves',exact:true}).click();
  await page.getByRole('row').filter({hasText:'Phase 5 original cycle'}).getByRole('button',{name:'Revise / reschedule'}).click();
  let dialog=page.getByRole('dialog'); await dialog.getByLabel('Revised reserve name').fill('Phase 5 next cycle');
  await dialog.getByLabel('Revised collection start').fill('2028-01-01'); await dialog.getByLabel('Actual scheduled renewal date').fill('2028-12-01');
  await dialog.getByLabel('Reason and authority to carry retained funding').fill('Authorized rollover of the unused 400 only');
  await dialog.getByRole('button',{name:'Save',exact:true}).click(); await expect(dialog).toHaveCount(0);
  const reserves=await get<{results:{id:number;name:string;progress:{consumed:string;designated:string}}[]}>(page,'/founders/reserves/');
  const retained=reserves.results.find(r=>r.name==='Phase 5 next cycle')!;
  expect(retained.progress.designated).toMatch(/^400(?:\.0+)?$/); expect(reserves.results.find(r=>r.id===original.id)!.progress.consumed).toMatch(/^800(?:\.0+)?$/);
  await page.getByRole('radio',{name:'Contribution Progress',exact:true}).click();
  await page.getByRole('button',{name:'Release unused funding',exact:true}).click(); dialog=page.getByRole('dialog');
  await dialog.getByLabel('Unused funding to release').fill('150'); await dialog.getByLabel('Reason and authority',{exact:true}).fill('Retained funding reallocated with authorization');
  await dialog.getByRole('button',{name:'Save',exact:true}).click(); await expect(dialog).toHaveCount(0);
  const after=await get<{count:number}>(page,'/accounting/journals/?page_size=1'); expect(after.count).toBe(before.count);
  const revised=await get<{progress:{designated:string}}>(page,`/founders/reserves/${retained.id}/`); expect(revised.progress.designated).toMatch(/^250(?:\.0+)?$/);
});

test('Phase 5 shell, routes and financial screens retain the approved geometry and themes',async({page})=>{
  for(const path of ['overview','contributions','expenses','sharing','settlements','loans','reimbursements','statements']){
    await page.goto(`/founder/${path}`); await expect(page.locator('main h1')).toBeVisible(); await expect(page.getByText('This page couldn’t load')).toHaveCount(0);
  }
  for(const path of ['shareholders','overview','capital','transfers','issuance','history']){
    await page.goto(`/ownership/${path}`); await expect(page.locator('main h1')).toBeVisible();
  }
  await page.goto('/founder/overview'); await page.evaluate(()=>document.fonts.ready);
  await expect(page.getByRole('img',{name:'Founder company activity'})).toBeVisible();
  await expect(page.getByRole('complementary',{name:'Sidebar'})).toHaveCSS('width','264px'); await expect(page.getByRole('banner')).toHaveCSS('height','56px');
  await page.screenshot({path:'test-results/phase5-founder-light.png'});
  await page.getByRole('button',{name:'Collapse sidebar'}).click(); await expect(page.getByRole('complementary',{name:'Sidebar'})).toHaveCSS('width','64px'); await page.screenshot({path:'test-results/phase5-founder-compact.png'});
  await page.getByRole('button',{name:'Expand sidebar'}).click(); await page.getByRole('button',{name:'Switch to dark mode'}).click(); await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.goto('/ownership/overview'); await expect(page.getByText('12500',{exact:true})).toBeVisible(); await page.screenshot({path:'test-results/phase5-ownership-dark.png'});
  await page.setViewportSize({width:390,height:844}); await page.goto('/founder/sharing'); await expect(page.getByText('Phase 5 equal sharing',{exact:true})).toBeVisible(); await page.screenshot({path:'test-results/phase5-founder-mobile.png'});
  // Preferences persist on the shared test account. Restore the established
  // light/expanded baseline before the Phase 1 shell regression starts.
  await page.setViewportSize({width:1440,height:900});
  const restored=page.waitForResponse(r=>r.url().endsWith('/api/v1/auth/me/') && r.request().method()==='PATCH');
  await page.getByRole('button',{name:'Switch to light mode'}).click();
  expect((await restored).ok()).toBe(true);
  await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  expect((await get<{preferences:{theme:string}}>(page,'/auth/me/')).preferences.theme).toBe('light');
  const response=await page.goto('/founder/not-a-section'); expect(response?.status()).toBe(404);
});
