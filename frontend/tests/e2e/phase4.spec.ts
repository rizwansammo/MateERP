import { createHash } from 'node:crypto';
import { expect, test, type Page, type Browser } from '@playwright/test';
import { apiPost, csrfHeaders, djangoShell, ensureUser, login, pngBuffer, strongPassword } from './support';

test.describe.configure({ mode: 'serial' });
const DAY = '2026-10-20';
let customer: number, invoice: number, extraInvoice: number, payment: number, receipt: number, vendor: number, bill: number, vendorPayment: number, project: number;
let bank: number, tax: number, revenue: number, expenseAccount: number;
let verifierPassword: string;
let originalPdf: string, originalHash: string, originalBranding: number;
const clientName = 'Phase 4 Acceptance Client'; const vendorName = 'Phase 4 Acceptance Supplier';

async function get<T>(page: Page, url: string): Promise<T> { const response = await page.request.get(`/api/v1${url}`); expect(response.ok(), await response.text()).toBe(true); return response.json(); }
async function post<T>(page: Page, url: string, data: unknown = {}): Promise<T> { const response = await apiPost(page.request, page.context(), `/api/v1${url}`, data); expect(response.ok(), await response.text()).toBe(true); return response.json(); }
async function verificationPage(browser: Browser) { const context = await browser.newContext({ storageState: { cookies: [], origins: [] } }); const page = await context.newPage(); await login(page, 'e2e-phase4-verifier', verifierPassword); await expect(page).toHaveURL(/dashboard/); return { context, page }; }
async function verify(browser: Browser, paymentId: number) {
  const signed = await verificationPage(browser); await signed.page.goto(`/sales/payments/${paymentId}`);
  await signed.page.getByRole('button', { name: 'Verify payment', exact: true }).click();
  const dialog = signed.page.getByRole('dialog'); await dialog.getByRole('checkbox').check();
  const response = signed.page.waitForResponse(r => r.url().endsWith(`/payments/${paymentId}/verify/`) && r.request().method() === 'POST', { timeout: 45_000 });
  await dialog.getByRole('button', { name: 'Verify & post' }).click();
  const verified = await response; expect(verified.ok(), await verified.text()).toBe(true);
  await expect(dialog).toHaveCount(0);
  const result = await get<{ status: string; receipt: { id: number }; journal: { id: string } }>(signed.page, `/billing/payments/${paymentId}/`);
  expect(result.status).toBe('verified'); await signed.context.close(); return result;
}

test('A — existing platform setup, customer and sales order through the UI', async ({ page }) => {
  test.setTimeout(120_000);
  const setup = JSON.parse(djangoShell(`
import json
from datetime import date
from types import SimpleNamespace
from django.conf import settings
assert settings.MATEERP_ENVIRONMENT == "e2e"
from apps.accounts.models import User, Role, Permission
from apps.company.models import CompanyProfile
from apps.company.services import create_company
from apps.accounting.models import Account, FiscalYear, TaxCode
from apps.accounting.services.setup import setup_chart, save_account, create_year, save_tax
from apps.banking.models import BankAccount
from apps.banking.services import save_account as save_bank
from apps.branding.models import BrandingVersion
from apps.branding.services import publish
from apps.approvals.models import ApprovalPolicy
r=SimpleNamespace(user=User.objects.get(username="e2e-admin"), META={})
if not CompanyProfile.objects.exists(): create_company(r,{"display_name":"NetaMate", "base_currency":"BDT", "time_zone":"Asia/Dhaka", "fiscal_year_start_month":1})
ApprovalPolicy.objects.update(is_required=False, approver_role=None, allow_self_approval=False)
chart={a.code:a for a in setup_chart(r)}
if not FiscalYear.objects.filter(start=date(2026,1,1)).exists(): create_year(r,date(2026,1,1))
for purpose,code,name,kind in [("receivable","1110","Trade receivables","asset"),("payable","2011","Trade payables","liability"),("customer_credit","2200","Customer credits","liability")]:
    if not Account.objects.filter(control=purpose).exists(): save_account(r,{"code":code,"name":name,"account_type":kind,"control":purpose})
b=BankAccount.objects.filter(name="Phase 4 acceptance bank").first()
if not b:
    bank_gl=save_account(r,{"code":"1087","name":"Phase 4 acceptance bank","account_type":"asset","currency":"BDT"})
    b=save_bank(r,{"name":"Phase 4 acceptance bank","kind":"bank","currency":"BDT","gl_account_id":bank_gl.pk})
t=TaxCode.objects.filter(code="VAT10").first()
if not t: t=save_tax(r,{"code":"VAT10","name":"VAT 10%","revision":{"effective_date":date(2026,1,1),"percent":"10","input_account_id":chart["1150"].pk,"output_account_id":chart["2100"].pk}})
if not BrandingVersion.objects.exists(): publish(r,label="Acceptance branding")
role,_=Role.objects.get_or_create(key="e2e-phase4-verifier", defaults={"name":"Payment verifier"})
role.permissions.set(Permission.objects.filter(code__in=["finance.view","payments.approve"]))
print(json.dumps({"bank":b.pk,"tax":t.pk,"revenue":chart["4100"].pk,"expense":chart["6100"].pk}))
`)) as { bank: number; tax: number; revenue: number; expense: number };
  ({ bank, tax, revenue } = setup); expenseAccount = setup.expense;
  verifierPassword = strongPassword(); ensureUser('e2e-phase4-verifier', 'e2e-phase4-verifier', verifierPassword);
  await page.goto('/sales/setup'); await page.getByRole('button', { name: 'Edit defaults' }).click();
  let dialog = page.getByRole('dialog'); await dialog.getByLabel('Default revenue account').selectOption(String(revenue)); await dialog.getByLabel('Default expense account').selectOption(String(expenseAccount)); await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toHaveCount(0);
  await page.goto('/sales/customers'); await page.getByRole('button', { name: 'New customer' }).click(); dialog = page.getByRole('dialog');
  await dialog.getByLabel('Customer / legal name').fill(clientName); await dialog.getByLabel('Email', { exact: true }).fill('client@example.test'); await dialog.getByLabel('Default currency').selectOption('BDT'); await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page).toHaveURL(/sales\/customers\/\d+/); customer = Number(new URL(page.url()).pathname.split('/').at(-1));
  await page.goto('/sales/orders'); await page.getByRole('button', { name: 'New sales order' }).click(); dialog = page.getByRole('dialog');
  await dialog.getByLabel('Customer', { exact: true }).selectOption(String(customer)); await dialog.getByLabel('Currency', { exact: true }).selectOption('BDT'); await dialog.getByLabel('Order title').fill('Implementation contract');
  await dialog.getByLabel('Line 1 description').fill('Implementation service'); await dialog.getByLabel('Line 1 unit price').fill('1000'); await dialog.getByLabel('Line 1 tax', { exact: true }).selectOption(String(tax)); await dialog.getByRole('button', { name: 'Save sales order' }).click(); await expect(dialog).toHaveCount(0);
  const row = page.getByRole('row').filter({ hasText: 'Implementation contract' }); await expect(row).toContainText('1,100.00');
  await row.getByRole('button', { name: 'Confirm', exact: true }).click(); await expect(row).toContainText('Confirmed');
  await row.getByRole('button', { name: 'Convert to invoice' }).click(); await expect(page).toHaveURL(/sales\/invoices\/\d+\/edit/); invoice = Number(new URL(page.url()).pathname.split('/')[3]);
});

test('B, C, G — draft, exact tax/discounts, immutable issuance and concurrent retries', async ({ page }) => {
  const before = await get<{ journal: unknown; status: string; total: string }>(page, `/billing/invoices/${invoice}/`); expect(before.journal).toBeNull(); expect(before.status).toBe('draft'); expect(before.total).toBe('1100.000000');
  const calc = await post<{ total: string; taxable: string; tax: string }>(page, '/sales/calculate/', { currency: 'BDT', date: DAY, lines: [{ quantity: '1', unit_price: '1000', discount_type: 'percent', discount_value: '10', tax_code_id: tax }], discount_type: 'percent', discount_value: '5' });
  expect(calc).toMatchObject({ taxable: '855.00', tax: '85.50', total: '940.50' });
  await page.goto(`/sales/invoices/${invoice}/edit`); await expect(page.getByLabel('Line 1 unit price')).toHaveValue('1000'); await page.getByLabel('Invoice date', { exact: true }).fill(DAY); await page.getByRole('button', { name: 'Save draft', exact: true }).click(); await expect(page).toHaveURL(new RegExp(`/sales/invoices/${invoice}$`));
  await page.getByRole('button', { name: 'Issue invoice', exact: true }).click(); await expect(page.getByRole('button', { name: 'Issue invoice', exact: true })).toHaveCount(0);
  const inv = await get<{ number: string; status: string; total: string; journal: { id: string }; snapshot: { lines: unknown[] }; pdf_url: string; pdf_status: string; branding_version: number }>(page, `/billing/invoices/${invoice}/`);
  expect(inv.status).toBe('issued'); expect(inv.pdf_status).toBe('ready'); expect(inv.journal.id).toBeTruthy(); originalBranding = inv.branding_version; originalPdf = inv.pdf_url;
  const pdf = await page.request.get(inv.pdf_url); expect(pdf.headers()['content-type']).toBe('application/pdf'); const pdfBytes = await pdf.body(); expect(pdfBytes.subarray(0, 5).toString()).toBe('%PDF-'); originalHash = createHash('sha256').update(pdfBytes).digest('hex');
  const repeat = await Promise.all([post<{ journal: { id: string } }>(page, `/billing/invoices/${invoice}/issue/`), post<{ journal: { id: string } }>(page, `/billing/invoices/${invoice}/issue/`)]); expect(repeat.map(i => i.journal.id)).toEqual([inv.journal.id, inv.journal.id]);
  const denied = await page.request.patch(`/api/v1/billing/invoices/${invoice}/`, { headers: await csrfHeaders(page.context()), data: { notes: 'Rewrite issued document', revision: 1 } }); expect(denied.status()).toBe(409);
  await page.screenshot({ path: 'test-results/phase4-invoice-light.png' });
});

test('D, E, F — partial payment recording, verification segregation and official receipt', async ({ page, browser }) => {
  await page.goto(`/sales/invoices/${invoice}`); await page.getByRole('button', { name: 'Record payment', exact: true }).first().click(); const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Amount received', { exact: true }).fill('440'); await dialog.getByLabel('Allocation 1 amount').fill('440'); await dialog.getByLabel('Receiving account', { exact: true }).selectOption(String(bank));
  const recorded = page.waitForResponse(r => r.url().endsWith('/api/v1/billing/payments/') && r.request().method() === 'POST'); await dialog.getByRole('button', { name: 'Record for verification' }).click(); const response = await recorded; const data = await response.json(); payment = data.id;
  await expect(page).toHaveURL(new RegExp(`/sales/payments/${payment}$`)); expect(data.status).toBe('pending_verification'); expect(data.journal).toBeNull(); expect(data.receipt).toBeNull();
  const own = await apiPost(page.request, page.context(), `/api/v1/billing/payments/${payment}/verify/`, {}); expect(own.status()).toBe(403);
  const replay = await post<{ id: number }>(page, '/billing/payments/', response.request().postDataJSON()); expect(replay.id).toBe(payment);
  const verified = await verify(browser, payment); receipt = verified.receipt.id;
  const inv = await get<{ amount_paid: string; outstanding: string; status: string }>(page, `/billing/invoices/${invoice}/`); expect(inv).toMatchObject({ amount_paid: '440.000000', outstanding: '660.000000', status: 'partially_paid' });
  await page.goto(`/sales/receipts/${receipt}`); await expect(page.getByRole('img', { name: 'Money receipt' })).toBeVisible(); await expect(page.getByRole('link', { name: /PDF/ }).first()).toBeVisible();
});

test('D, G, Q — multi-invoice settlement and exact AR / customer-credit reconciliation', async ({ page, browser }) => {
  const extra = await post<{ id: number }>(page, '/billing/invoices/', { customer_id: customer, issue_date: DAY, lines: [{ description: 'Additional service', unit_price: '100', tax_code_id: tax, revenue_account_id: revenue }] }); extraInvoice = extra.id; await post(page, `/billing/invoices/${extraInvoice}/issue/`);
  const p = await post<{ id: number }>(page, '/billing/payments/', { posting_key: 'phase4-multiple-allocations', customer_id: customer, bank_account_id: bank, payment_date: DAY, amount: '770', allocations: [{ invoice_id: invoice, amount: '660' }, { invoice_id: extraInvoice, amount: '110' }] }); await verify(browser, p.id);
  const inv = await get<{ outstanding: string; status: string }>(page, `/billing/invoices/${invoice}/`); expect(inv.outstanding).toBe('0.000000'); expect(inv.status).toBe('paid');
  const check = await get<Record<string, { difference: string }>>(page, '/billing/reconciliation/'); for (const value of Object.values(check)) expect(value.difference).toMatch(/^0(?:\.0+)?$/);
  const files = await get<{ results: { kind: string }[] }>(page, `/documents/?area=client&invoice=${extraInvoice}`); expect(files.results.some(d => d.kind === 'receipt')).toBe(true);
});

test('H — issued credit notes remain distinct from cash refunds', async ({ page }) => {
  const note = await post<{ status: string; credit_amount: string; id: number }>(page, `/billing/invoices/${invoice}/credit-notes/`, { posting_key: 'phase4-credit-paid', issue_date: DAY, reason: 'Acceptance service concession', lines: [{ invoice_line_id: (await get<{ lines: { id: number }[] }>(page, `/billing/invoices/${invoice}/`)).lines[0]!.id, amount: '110' }] });
  expect(note.status).toBe('issued'); expect(note.credit_amount).toBe('110.000000');
  await page.goto('/sales/credits'); await expect(page.getByText('Acceptance service concession').first()).toBeVisible();
  const refund = await post<{ status: string; journal: unknown }>(page, '/billing/refunds/', { posting_key: 'phase4-refund-paid', customer_id: customer, bank_account_id: bank, refund_date: DAY, amount: '110', reason: 'Return customer credit', method: 'bank_transfer' }); expect(refund.status).toBe('paid'); expect(refund.journal).not.toBeNull();
  const check = await get<Record<string, { difference: string }>>(page, '/billing/reconciliation/'); for (const value of Object.values(check)) expect(value.difference).toMatch(/^0(?:\.0+)?$/);
});

test('I, J — vendor bill and reviewed payment through the purchasing interface', async ({ page }) => {
  await page.goto('/purchases/vendors'); await page.getByRole('button', { name: 'New vendor', exact: true }).click(); let dialog = page.getByRole('dialog'); await dialog.getByLabel('Vendor name').fill(vendorName); await dialog.getByLabel('Default currency').selectOption('BDT'); await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toHaveCount(0);
  const vendors = await get<{ results: { id: number; name: string }[] }>(page, '/purchasing/vendors/'); vendor = vendors.results.find(v => v.name === vendorName)!.id;
  await page.goto('/purchases/bills'); await page.getByRole('button', { name: 'New vendor bill' }).click(); dialog = page.getByRole('dialog'); await dialog.getByLabel('Vendor', { exact: true }).selectOption(String(vendor)); await dialog.getByLabel('Vendor invoice reference').fill('SUPPLIER-ACCEPTANCE-001'); await dialog.getByLabel('Bill date', { exact: true }).fill(DAY); await dialog.getByLabel('Due date', { exact: true }).fill(DAY); await dialog.getByLabel('Line 1 description').fill('Hosting services'); await dialog.getByLabel('Line 1 unit price').fill('200'); await dialog.getByLabel('Line 1 tax', { exact: true }).selectOption(String(tax)); await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toHaveCount(0);
  const bills = await get<{ results: { id: number; vendor_reference: string }[] }>(page, '/purchasing/bills/'); bill = bills.results.find(b => b.vendor_reference === 'SUPPLIER-ACCEPTANCE-001')!.id;
  await page.goto(`/purchases/bills/${bill}`); await page.getByRole('button', { name: 'Post bill', exact: true }).click(); await page.getByRole('dialog').getByRole('button', { name: 'Post', exact: true }).click(); await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'Pay vendor', exact: true }).click(); dialog = page.getByRole('dialog'); await dialog.getByLabel('Paying account', { exact: true }).selectOption(String(bank)); await dialog.getByRole('button', { name: 'Preview payment' }).click(); await expect(dialog.getByText(/Reviewed preview/)).toBeVisible(); await dialog.getByRole('button', { name: 'Confirm payment' }).click(); await expect(dialog).toHaveCount(0);
  const paid = await get<{ status: string; outstanding: string }>(page, `/purchasing/bills/${bill}/`); expect(paid).toMatchObject({ status: 'paid', outstanding: '0.000000' });
  const pays = await get<{ results: { id: number; vendor_id: number }[] }>(page, '/purchasing/payments/'); vendorPayment = pays.results.find(p => p.vendor_id === vendor)!.id;
  const duplicate = await apiPost(page.request, page.context(), '/api/v1/purchasing/bills/', { vendor_id: vendor, vendor_reference: 'SUPPLIER-ACCEPTANCE-001', bill_date: DAY, lines: [{ description: 'Duplicate', unit_price: '10', account_id: expenseAccount }] }); expect(duplicate.status()).toBe(409);
});

test('K — paid and accrued operating expenses remain real company obligations', async ({ page }) => {
  await page.goto('/purchases/expenses'); await page.getByRole('button', { name: 'Record expense' }).click(); const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Description', { exact: true }).fill('Acceptance paid connectivity'); await dialog.getByLabel('Amount', { exact: true }).fill('25'); await dialog.getByLabel('Funding', { exact: true }).selectOption('paid'); await dialog.getByLabel('Paying account', { exact: true }).selectOption(String(bank)); await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toHaveCount(0);
  await page.getByRole('link', { name: 'Draft', exact: true }).first().click(); await page.getByRole('button', { name: 'Post expense' }).click(); await page.getByRole('dialog').getByRole('button', { name: 'Post', exact: true }).click(); await expect(page.getByRole('dialog')).toHaveCount(0); await expect(page.getByText('Paid', { exact: true }).first()).toBeVisible();
  const accrued = await post<{ id: number; journal: unknown }>(page, '/purchasing/expenses/', { vendor_id: vendor, expense_date: DAY, description: 'Acceptance accrued subscription', amount: '30', payment_mode: 'accrued', account_id: expenseAccount }); expect(accrued.journal).toBeNull(); await post(page, `/purchasing/expenses/${accrued.id}/post/`);
  const ap = await get<{ difference: string; subledger: string }>(page, '/purchasing/reconciliation/'); expect(ap.difference).toMatch(/^0(?:\.0+)?$/); expect(ap.subledger).toBe('30.000000');
});

test('L, M — recurring billing and expense runs generate drafts exactly once', async ({ page }) => {
  await page.goto('/sales/recurring'); await page.getByRole('button', { name: 'New recurring invoice' }).click(); let dialog = page.getByRole('dialog'); await dialog.getByLabel('Schedule name').fill('Acceptance recurring service'); await dialog.getByLabel('Customer', { exact: true }).selectOption(String(customer)); await dialog.getByLabel('Start date', { exact: true }).fill(DAY); await dialog.getByLabel('Line 1 description').fill('Monthly support'); await dialog.getByLabel('Line 1 unit price').fill('50'); await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toHaveCount(0);
  let row = page.getByRole('row').filter({ hasText: 'Acceptance recurring service' }); await row.getByRole('button', { name: 'Run due', exact: true }).click(); await page.getByRole('dialog').getByRole('button', { name: 'Run due', exact: true }).click(); await expect(page.getByRole('dialog')).toHaveCount(0);
  const schedules = await get<{ results: { id: number; name: string }[] }>(page, '/billing/recurring/'); const s = schedules.results.find(s => s.name === 'Acceptance recurring service')!; await post(page, '/billing/recurring/run/', { until: DAY, schedule_ids: [s.id] }); const history = await get<{ runs: { status: string }[] }>(page, `/billing/recurring/${s.id}/`); expect(history.runs).toHaveLength(1); expect(history.runs[0]!.status).toBe('drafted');
  await page.goto('/purchases/recurring'); await page.getByRole('button', { name: 'New recurring expense' }).click(); dialog = page.getByRole('dialog'); await dialog.getByLabel('Schedule name').fill('Acceptance hosting renewal'); await dialog.getByLabel('Vendor', { exact: true }).selectOption(String(vendor)); await dialog.getByLabel('Start date', { exact: true }).fill(DAY); await dialog.getByLabel('Description', { exact: true }).fill('Hosting renewal'); await dialog.getByLabel('Amount', { exact: true }).fill('40'); await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toHaveCount(0);
  row = page.getByRole('row').filter({ hasText: 'Acceptance hosting renewal' }); await row.getByRole('button', { name: 'Run due', exact: true }).click(); await page.getByRole('dialog').getByRole('button', { name: 'Run due', exact: true }).click(); await expect(page.getByRole('dialog')).toHaveCount(0);
  const expenses = await get<{ results: { id: number; name: string }[] }>(page, '/purchasing/recurring/'); const es = expenses.results.find(s => s.name === 'Acceptance hosting renewal')!; await post(page, '/purchasing/recurring/run/', { until: DAY, schedule_ids: [es.id] }); const eh = await get<{ runs: { status: string }[] }>(page, `/purchasing/recurring/${es.id}/`); expect(eh.runs).toHaveLength(1); expect(eh.runs[0]!.status).toBe('drafted');
});

test('A — project milestones create linked invoice drafts without premature revenue', async ({ page }) => {
  await page.goto('/sales/projects'); await page.getByRole('button', { name: 'New project' }).click(); const dialog = page.getByRole('dialog'); await dialog.getByLabel('Project name').fill('Acceptance implementation'); await dialog.getByLabel('Project reference').fill('ACCEPT-PROJECT'); await dialog.getByLabel('Customer', { exact: true }).selectOption(String(customer)); await dialog.getByLabel('Contract value').fill('5000'); await dialog.getByRole('button', { name: 'Add milestone' }).click(); await dialog.getByLabel('Milestone 1 name').fill('Delivery'); await dialog.getByLabel('Milestone 1 percent').fill('100'); await dialog.getByRole('button', { name: 'Save', exact: true }).click(); await expect(dialog).toHaveCount(0);
  await page.getByRole('link', { name: 'Acceptance implementation', exact: true }).click(); await expect(page).toHaveURL(/sales\/projects\/\d+/); project = Number(new URL(page.url()).pathname.split('/').at(-1)); await page.getByRole('button', { name: 'Create invoice', exact: true }).click(); await expect(page).toHaveURL(/sales\/invoices\/\d+\/edit/); const financials = await get<{ invoiced: string }>(page, `/billing/projects/${project}/financials/`); expect(financials.invoiced).toBe('0');
});

test('N, O, P — private document filing, evidence access, preview and archive', async ({ page, browser }) => {
  await page.goto(`/client-documents?year=2026&customer=${customer}&invoice=${invoice}`); await page.getByRole('button', { name: 'Upload documents' }).click(); let dialog = page.getByRole('dialog'); await dialog.getByLabel('Document type').selectOption('bank_proof'); await dialog.getByLabel('Title', { exact: true }).fill('Acceptance internal bank evidence'); await dialog.getByLabel('File', { exact: true }).setInputFiles({ name: 'evidence.png', mimeType: 'image/png', buffer: pngBuffer() }); await dialog.getByRole('button', { name: 'Upload', exact: true }).click(); await expect(dialog).toHaveCount(0);
  await page.getByLabel('Search documents').fill('Acceptance internal bank evidence'); const row = page.getByRole('row').filter({ hasText: 'Acceptance internal bank evidence' }); await row.getByRole('button', { name: 'Preview', exact: true }).click(); await expect(page.getByRole('dialog', { name: 'Acceptance internal bank evidence' })).toBeVisible(); await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0);
  const files = await get<{ results: { id: number; url: string; download_url: string }[] }>(page, `/documents/?area=client&search=Acceptance%20internal%20bank%20evidence`); const proof = files.results[0]!;
  const password = strongPassword(); ensureUser('e2e-phase4-viewer', 'viewer', password); const viewer = await browser.newContext({ storageState: { cookies: [], origins: [] } }); const vp = await viewer.newPage(); await login(vp, 'e2e-phase4-viewer', password); await expect(vp).toHaveURL(/dashboard/); expect((await vp.request.get(`/api/v1/documents/${proof.id}/`)).status()).toBe(404); expect((await vp.request.get(proof.url)).status()).toBe(404); expect((await vp.request.get(proof.download_url)).status()).toBe(404); await viewer.close();
  await row.getByRole('button', { name: 'Archive', exact: true }).click(); dialog = page.getByRole('dialog'); await dialog.getByLabel('Reason', { exact: true }).fill('Acceptance archive retention'); await dialog.getByRole('button', { name: 'Archive document' }).click(); await expect(dialog).toHaveCount(0); await expect(row).toHaveCount(0);
  await page.goto(`/vendor-documents?year=2026&month=10&vendor=${vendor}`); await page.getByRole('button', { name: 'Upload documents' }).click(); dialog = page.getByRole('dialog'); await dialog.getByLabel('Document type').selectOption('vendor_receipt'); await dialog.getByLabel('Vendor payment', { exact: true }).selectOption(String(vendorPayment)); await dialog.getByLabel('Title', { exact: true }).fill('Acceptance vendor payment receipt'); await dialog.getByLabel('File', { exact: true }).setInputFiles({ name: 'supplier-receipt.png', mimeType: 'image/png', buffer: pngBuffer() }); await dialog.getByRole('button', { name: 'Upload', exact: true }).click(); await expect(dialog).toHaveCount(0); await page.getByLabel('Search documents').fill('Acceptance vendor payment receipt'); await expect(page.getByRole('row').filter({ hasText: 'Acceptance vendor payment receipt' })).toBeVisible();
  await page.screenshot({ path: 'test-results/phase4-vendor-documents.png' });
});

test('R — historical FX valuation, explicit vendor-payment confirmation and period locks', async ({ page, browser }) => {
  const currencies = await page.request.patch('/api/v1/settings/business/', { headers: await csrfHeaders(page.context()), data: { enabled_currencies: ['BDT', 'USD'] } }); expect(currencies.ok()).toBe(true);
  await post(page, '/accounting/exchange-rates/', { currency: 'USD', effective_date: DAY, value: '120', source: 'Acceptance historical rate' });
  const account = await post<{ id: number }>(page, '/accounting/accounts/', { code: '1088', name: 'Acceptance USD bank', account_type: 'asset', currency: 'USD' });
  const usdBank = await post<{ id: number }>(page, '/banking/accounts/', { name: 'Acceptance USD bank', kind: 'bank', currency: 'USD', gl_account_id: account.id });
  const foreign = await post<{ id: number }>(page, '/billing/invoices/', { customer_id: customer, currency: 'USD', issue_date: DAY, lines: [{ description: 'Foreign service', unit_price: '10', revenue_account_id: revenue }] }); await post(page, `/billing/invoices/${foreign.id}/issue/`);
  const foreignBill = await post<{ id: number }>(page, '/purchasing/bills/', { vendor_id: vendor, vendor_reference: 'ACCEPTANCE-USD-BILL', currency: 'USD', bill_date: DAY, lines: [{ description: 'Foreign hosting', unit_price: '5', account_id: expenseAccount }] }); await post(page, `/purchasing/bills/${foreignBill.id}/post/`);
  await post(page, '/accounting/exchange-rates/', { currency: 'USD', effective_date: DAY, value: '130', source: 'Acceptance collection rate' });
  const incoming = await post<{ id: number }>(page, '/billing/payments/', { posting_key: 'phase4-foreign-collection', customer_id: customer, bank_account_id: usdBank.id, payment_date: DAY, amount: '10', allocations: [{ invoice_id: foreign.id, amount: '10' }] }); await verify(browser, incoming.id);
  const historical = await get<{ exchange_rate: string; base_total: string; outstanding: string }>(page, `/billing/invoices/${foreign.id}/`); expect(historical.exchange_rate).toBe('120.000000000000'); expect(historical.base_total).toBe('1200.000000'); expect(historical.outstanding).toBe('0.000000');
  await page.goto(`/purchases/bills/${foreignBill.id}`); await page.getByRole('button', { name: 'Pay vendor', exact: true }).click(); const dialog = page.getByRole('dialog'); await dialog.getByLabel('Paying account', { exact: true }).selectOption(String(usdBank.id)); await dialog.getByRole('button', { name: 'Preview payment' }).click();
  await expect(dialog.getByText(/Reviewed preview/)).toBeVisible(); await expect(dialog.getByRole('button', { name: 'Confirm payment' })).toBeDisabled(); await dialog.getByRole('checkbox', { name: 'I reviewed and accept the disclosed FX difference' }).check(); await dialog.getByRole('button', { name: 'Confirm payment' }).click(); await expect(dialog).toHaveCount(0);
  expect((await get<{ status: string }>(page, `/purchasing/bills/${foreignBill.id}/`)).status).toBe('paid');
  const periods = await get<{ results: { id: number; start: string; end: string }[] }>(page, '/accounting/periods/?page_size=100'); const period = periods.results.find(p => p.start <= DAY && p.end >= DAY); expect(period).toBeDefined();
  const draft = await post<{ id: number }>(page, '/billing/invoices/', { customer_id: customer, issue_date: DAY, lines: [{ description: 'Closed-period boundary', unit_price: '1', revenue_account_id: revenue }] });
  await post(page, `/accounting/periods/${period!.id}/close/`, { reason: 'Acceptance period lock' });
  const closedPeriod = await apiPost(page.request, page.context(), `/api/v1/billing/invoices/${draft.id}/issue/`, {});
  expect(closedPeriod.status()).toBe(400); expect(JSON.stringify(await closedPeriod.json())).toContain('open accounting period');
  const blocked = await get<{ journal: unknown; number: unknown }>(page, `/billing/invoices/${draft.id}/`); expect(blocked.journal).toBeNull(); expect(blocked.number).toBeNull();
  await post(page, `/accounting/periods/${period!.id}/reopen/`, { reason: 'Acceptance reviewed reopening' }); await post(page, `/billing/invoices/${draft.id}/issue/`);
});

test('Q, S, T — approval affects issuance and published branding cannot rewrite history', async ({ page, browser }) => {
  const headers = await csrfHeaders(page.context()); const policy = await page.request.patch('/api/v1/approvals/policies/invoices/', { headers, data: { is_required: true, is_active: true, allow_self_approval: false, amount_threshold: '0' } }); expect(policy.ok()).toBe(true);
  const draft = await post<{ id: number }>(page, '/billing/invoices/', { customer_id: customer, issue_date: DAY, lines: [{ description: 'Approval controlled service', unit_price: '20', revenue_account_id: revenue }] }); const pending = await post<{ status: string; approval_id: number; journal: unknown }>(page, `/billing/invoices/${draft.id}/approve/`); expect(pending.status).toBe('pending_approval'); expect(pending.journal).toBeNull();
  expect((await apiPost(page.request, page.context(), `/api/v1/billing/invoices/${draft.id}/issue/`, {})).status()).toBe(409);
  const password = strongPassword(); ensureUser('e2e-phase4-approver', 'administrator', password); const context = await browser.newContext({ storageState: { cookies: [], origins: [] } }); const approver = await context.newPage(); await login(approver, 'e2e-phase4-approver', password); await expect(approver).toHaveURL(/dashboard/); await approver.goto('/settings/approvals'); const row = approver.getByRole('row').filter({ hasText: 'Approve invoice for' }); await expect(row.getByRole('link', { name: 'Review financial record' })).toHaveAttribute('href', `/sales/invoices/${draft.id}/`); await row.getByRole('button', { name: 'Approve', exact: true }).click(); await approver.getByRole('dialog').getByRole('button', { name: 'Approve', exact: true }).click(); await expect(row).toHaveCount(0); await context.close();
  await post(page, `/billing/invoices/${draft.id}/issue/`); await page.request.patch('/api/v1/approvals/policies/invoices/', { headers: await csrfHeaders(page.context()), data: { is_required: false } });
  const branding = await get<{ draft: { config: Record<string, unknown> } }>(page, '/branding/'); const patch = await page.request.put('/api/v1/branding/draft/', { headers: await csrfHeaders(page.context()), data: { config: { ...branding.draft.config, footer_text: 'New branding after issuance' } } }); expect(patch.ok(), await patch.text()).toBe(true); await post(page, '/branding/publish/', { label: 'After issued documents' });
  const preserved = await get<{ branding_version: number; pdf_url: string }>(page, `/billing/invoices/${invoice}/`); expect(preserved.branding_version).toBe(originalBranding); expect(preserved.pdf_url).toBe(originalPdf); const pdf = await page.request.get(originalPdf); expect(createHash('sha256').update(await pdf.body()).digest('hex')).toBe(originalHash);
  const checks = await get<Record<string, { difference: string }>>(page, '/billing/reconciliation/'); for (const check of Object.values(checks)) expect(check.difference).toMatch(/^0(?:\.0+)?$/);
  expect((await get<{ difference: string }>(page, '/purchasing/reconciliation/')).difference).toMatch(/^0(?:\.0+)?$/);
});

test('U, V — Phase 4 routes, planned Phase 6 purchasing, themes and responsive shell', async ({ page }) => {
  test.setTimeout(120_000);
  for (const route of ['/sales/overview', '/sales/customers', '/sales/orders', '/sales/invoices', '/sales/payments', '/sales/receipts', '/sales/recurring', '/sales/credits', '/sales/projects', '/purchases/overview', '/purchases/expenses', '/purchases/recurring', '/purchases/vendors', '/purchases/bills', '/purchases/history', '/client-documents', '/vendor-documents']) { await page.goto(route); await expect(page.getByRole('heading', { level: 1 })).toBeVisible(); await expect(page.getByText('Application error')).toHaveCount(0); }
  await page.goto('/purchases/orders'); await expect(page.getByText(/Phase 6/).first()).toBeVisible();
  await page.goto('/sales/overview'); await expect(page.getByRole('img', { name: 'Invoiced vs collected' })).toBeVisible(); await page.evaluate(() => document.fonts.ready); await page.screenshot({ path: 'test-results/phase4-sales-light.png' });
  await expect(page.getByRole('complementary', { name: 'Sidebar' })).toHaveCSS('width', '264px'); await expect(page.getByRole('banner')).toHaveCSS('height', '56px');
  await page.getByRole('button', { name: 'Collapse sidebar' }).click(); await expect(page.getByRole('complementary', { name: 'Sidebar' })).toHaveCSS('width', '64px'); await page.screenshot({ path: 'test-results/phase4-sales-compact.png' }); await page.getByRole('button', { name: 'Expand sidebar' }).click();
  await page.getByRole('button', { name: 'Switch to dark mode' }).click(); await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark'); await page.screenshot({ path: 'test-results/phase4-sales-dark.png' });
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto('/sales/invoices'); await expect(page.getByRole('heading', { name: 'Invoices', exact: true })).toBeVisible(); await page.screenshot({ path: 'test-results/phase4-mobile.png' });
  await page.setViewportSize({ width: 1440, height: 900 }); await page.getByRole('button', { name: 'Switch to light mode' }).click();
  await page.goto('/purchases/overview'); await expect(page.getByRole('img', { name: 'Monthly spend by category' })).toBeVisible(); await page.screenshot({ path: 'test-results/phase4-purchases-light.png' });
  await page.goto('/client-documents'); await expect(page.getByRole('button', { name: '2026', exact: false }).first()).toBeVisible(); await page.screenshot({ path: 'test-results/phase4-client-documents.png' });
});

