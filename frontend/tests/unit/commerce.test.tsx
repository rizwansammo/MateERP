import { renderHook, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { OrdersPage } from '@/features/sales/Orders';
import { CustomersPage } from '@/features/sales/Customers';
import { ReceiptsPage } from '@/features/sales/Receipts';
import { RecordPaymentDrawer } from '@/features/sales/Payments';
import { OverviewPage } from '@/features/sales/Overview';
import { PayablesPage } from '@/features/purchases/Payables';
import { RecurringExpensesPage } from '@/features/purchases/Recurring';
import { UploadDrawer } from '@/features/filing/UploadDrawer';
import { DocumentExplorer, clientFolders, vendorFolders } from '@/features/filing/Explorer';
import { FileViewer } from '@/features/commerce/FileViewer';
import { blankLine, toPayload, useCalculation } from '@/features/commerce/lines';
import { sumDecimals, trimDecimal } from '@/features/commerce/shared';
import type { FiledDocument } from '@/features/commerce/types';
import { body, FormDrawer } from '@/features/commerce/forms';
import { amountInWordsDecimal } from '@/features/documents/money';
import { MonthlyChart, BreakdownChart } from '@/features/commerce/Charts';
import { PlannedModule } from '@/features/system/PlannedModule';
import { findNavItem } from '@/lib/navigation';

import { makeUser, mockApi, renderWithAuth, viewerUser } from './helpers';

const page = <T,>(results: T[]) => ({ count: results.length, page: 1, page_size: 25, total_pages: 1, results });
const common = { '/auth/me/': makeUser(), '/accounting/config/': { base_currency: 'BDT', enabled_currencies: ['BDT'] }, '/reference/currencies/': [{ code: 'BDT', symbol: '৳' }] };

describe('posted financial charts', () => {
  it('renders negative reversals and very large exact amounts without invalid coordinates', () => {
    mockApi(common);
    const { container } = renderWithAuth(<MonthlyChart title="Posted activity" subtitle="Historical values" points={[{month:'2026-10', revenue:'999999999999999999.990000', costs:'1.000000'}, {month:'2026-11', revenue:'-2.000000', costs:'-1.000000'}]} series={[{key:'revenue',label:'Revenue'},{key:'costs',label:'Costs'}]} stacked currency="BDT" />);
    expect(screen.getByRole('img', {name:'Posted activity'})).toBeInTheDocument();
    const bars = container.querySelectorAll('rect'); expect(bars).toHaveLength(4);
    for(const bar of bars) for(const attribute of ['x','y','width','height']) expect(Number.isFinite(Number(bar.getAttribute(attribute)))).toBe(true);
    expect(container.innerHTML).toContain('999,999,999,999,999,999.99');
  });
  it('shows honest empty activity and the prototype aging counts', () => {
    mockApi(common);
    renderWithAuth(<><MonthlyChart title="Empty activity" subtitle="Fiscal year" points={[{month:'2026-10',collected:'0'}]} series={[{key:'collected',label:'Collected'}]}/><BreakdownChart aging title="Aging" subtitle="Historical AR" rows={[{label:'Current',amount:'0',count:0},{label:'1–30 days',amount:'12.34',count:2}]} currency="BDT"/></>);
    expect(screen.getByText('No posted activity in this fiscal year')).toBeInTheDocument(); expect(screen.getByText('2 invoices')).toBeInTheDocument();
  });
});

it('keeps purchase orders in Phase 6 without labeling working purchases sections as planned', () => {
  mockApi(common); const item = findNavItem('purchases');
  renderWithAuth(<PlannedModule item={item} group="Finance" current={item.subs!.find(s => s.slug === 'orders')!}/>);
  expect(screen.getByTestId('planned-notice')).toHaveTextContent('Purchase Orders is scheduled for Phase 6');
  expect(screen.queryByRole('cell', {name:'Expenses'})).not.toBeInTheDocument();
});

it('asks before discarding an edited sales order', async () => {
  mockApi({ ...common, '/sales/orders/': page([]), '/sales/customers/': page([]), '/accounting/accounts/': page([]), '/accounting/taxes/': page([]), '/sales/items/': page([]) });
  renderWithAuth(<OrdersPage/>);
  await userEvent.click(screen.getByRole('button', {name:'New sales order'}));
  await userEvent.type(screen.getByLabelText('Order title'), 'Unsubmitted order');
  await userEvent.click(screen.getByRole('button', {name:'Cancel'}));
  expect(await screen.findByRole('dialog', {name:'Discard unsaved order changes?'})).toBeVisible();
  await userEvent.click(screen.getByRole('button', {name:'Discard'}));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('retains an edited payment when discard is cancelled', async () => {
  mockApi({ ...common, '/sales/customers/': page([]), '/banking/accounts/': page([]) });
  const close = vi.fn(); renderWithAuth(<RecordPaymentDrawer onClose={close}/>);
  await userEvent.type(screen.getByLabelText('Amount received'), '100');
  await userEvent.click(screen.getByRole('button', {name:'Cancel'}));
  expect(await screen.findByRole('dialog', {name:'Discard unsaved payment?'})).toBeVisible();
  await userEvent.click(within(screen.getByRole('dialog', {name:'Discard unsaved payment?'})).getByRole('button', {name:'Cancel'}));
  expect(close).not.toHaveBeenCalled(); expect(screen.getByLabelText('Amount received')).toHaveValue('100');
});

describe('exact commercial values', () => {
  it('renders large receipt amounts in words without lossy conversion', () => {
    expect(amountInWordsDecimal('100000000000.010000', 'BDT')).toBe('Taka Ten Thousand Crore and One Poisha Only');
    expect(amountInWordsDecimal('1000000000000.010000', 'USD')).toBe('One Trillion US Dollars and One Cents Only');
    expect(amountInWordsDecimal('123.000000', 'JPY')).toBe('One Hundred Twenty-Three JPY Only');
  });
  it('preserves business tax identifiers as text while converting relation IDs', () => {
    expect(body({ tax_id: 'BD-001230', customer_id: '42', vendor_id: '', amount: '0.10' })).toEqual({ tax_id: 'BD-001230', customer_id: 42, vendor_id: null, amount: '0.10' });
    expect(body({ tax_id: '' })).toEqual({ tax_id: '' });
  });
  it('sums credits and amounts beyond safe JavaScript integers', () => {
    expect(sumDecimals(['999999999999999999.990000', '0.010000', '-10.000000'])).toBe('999999999999999990.000000');
    expect(sumDecimals(['0.10', '0.20', '-0.30'])).toBe('0.000000');
  });
  it('trims fractional zeros without shortening integer prices', () => {
    expect(trimDecimal('1000')).toBe('1000'); expect(trimDecimal('1000.000000')).toBe('1000');
  });
  it('sends exact prices, discounts and quantities to the server', () => {
    const result = toPayload([{ ...blankLine(), description: 'Service', quantity: '1.125', unit_price: '9999999999999999.99', account_id: '8', tax_code_id: '3', discount_value: '0.01' }], 'revenue_account_id');
    expect(result[0]).toMatchObject({ quantity: '1.125', unit_price: '9999999999999999.99', revenue_account_id: 8, tax_code_id: 3, discount_value: '0.01' });
  });
  it('clears a stale calculation immediately when input changes', async () => {
    mockApi({ 'POST /sales/calculate/': { total: '110.000000', lines: [], taxes: [] } });
    const { result, rerender } = renderHook(({ price }) => useCalculation({ currency: 'BDT', date: '2026-10-10', lines: [{ ...blankLine(), description: 'Service', unit_price: price }], pricesIncludeTax: false }), { initialProps: { price: '100' } });
    await waitFor(() => expect(result.current.result?.total).toBe('110.000000'));
    rerender({ price: '200' }); expect(result.current.result).toBeNull();
  });
});

it('shows the persisted order total instead of a line count', async () => {
  mockApi({ ...common, '/sales/orders/': page([{ id: 9, number: 'SO-2026-9', customer_name: 'Real client', title: 'Contract', order_date: '2026-10-10', status: 'invoiced', currency: 'BDT', lines: [], total: '12345.670000' }]) });
  renderWithAuth(<OrdersPage />);
  expect(await screen.findByText('BDT 12,345.67')).toBeInTheDocument();
  expect(screen.queryByRole('columnheader', { name: 'Lines' })).not.toBeInTheDocument();
});
it('submits the displayed base currency even when settings arrive after the form opens', async () => {
  mockApi(common); const save = vi.fn().mockResolvedValue({ id: 1 });
  renderWithAuth(<FormDrawer title="New record" eyebrow="Test" initial={{ currency: '', name: '' }} fields={[{ key: 'currency', label: 'Currency', type: 'select', options: [{ value: 'BDT', label: 'BDT' }] }, { key: 'name', label: 'Name' }]} onSave={save} onClose={vi.fn()} />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled());
  await userEvent.type(screen.getByLabelText('Name'), 'Keep entered data'); await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(save).toHaveBeenCalledWith({ currency: 'BDT', name: 'Keep entered data' }));
});
it('lets a viewer browse customers without a creation action', async () => {
  mockApi({ ...common, '/auth/me/': viewerUser, '/sales/customers/': page([{ id: 4, code: 'C-4', name: 'Visible customer', currency: 'BDT', payment_terms_days: 30, is_active: true }]) });
  renderWithAuth(<CustomersPage />, viewerUser);
  expect(await screen.findByRole('link', { name: 'Visible customer' })).toHaveAttribute('href', '/sales/customers/4');
  expect(screen.queryByRole('button', { name: 'New customer' })).not.toBeInTheDocument();
});
it('uses actual backend overview figures and shows reconciliation differences', async () => {
  mockApi({ ...common, '/billing/overview/': { base_currency: 'BDT', outstanding: '75', overdue: '25', overdue_count: 1, open_count: 2, invoiced_this_month: '100', collected_this_month: '25', pending_verification: 1, drafts: 0 }, '/billing/reconciliation/': { receivable: { ledger: '75', subledger: '75', difference: '0' } }, '/billing/invoices/': page([]) });
  renderWithAuth(<OverviewPage />);
  expect(await screen.findByText('2 open invoices')).toBeInTheDocument();
  expect(await screen.findByText(/General ledger BDT 75.00/)).toBeInTheDocument();
});
it('links official receipt PDFs to the stored server file', async () => {
  mockApi({ ...common, '/billing/receipts/': page([{ id: 3, number: 'MR-2026-3', status: 'issued', issue_date: '2026-10-10', customer_name: 'Client', payment_id: 2, payment_number: 'PAY-2', amount: '10', currency: 'BDT', pdf_status: 'ready', pdf_url: '/api/v1/files/official/content/' }]) });
  renderWithAuth(<ReceiptsPage />);
  expect(await screen.findByRole('link', { name: 'Open PDF' })).toHaveAttribute('href', '/api/v1/files/official/content/');
});
it('does not offer bill mutation controls to a viewer', async () => {
  mockApi({ ...common, '/auth/me/': viewerUser, '/purchasing/bills/': page([]) }); renderWithAuth(<PayablesPage kind="bills" />, viewerUser);
  expect(await screen.findByText('Nothing here yet.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'New vendor bill' })).not.toBeInTheDocument();
});
it('keeps recurring expense generation restricted', async () => {
  mockApi({ ...common, '/auth/me/': viewerUser, '/purchasing/recurring/': page([{ id: 3, name: 'Hosting renewal', vendor_name: 'Supplier', frequency: 'monthly', interval: 1, next_run_date: '2026-11-10', status: 'active' }]) });
  renderWithAuth(<RecurringExpensesPage />, viewerUser);
  expect(await screen.findByText('Hosting renewal')).toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Run due' })).not.toBeInTheDocument();
});
it('shows server errors instead of a fabricated empty directory', async () => {
  mockApi({ ...common, '/billing/receipts/': [503, { error: { code: 'unavailable', message: 'Service unavailable', details: null, request_id: 'test' } }] });
  renderWithAuth(<ReceiptsPage />); expect(await screen.findByText('Service unavailable')).toBeInTheDocument();
});

describe('document filing', () => {
  it('builds client invoice and vendor month hierarchies from API counts', () => {
    const c = clientFolders([{ year: 2026, count: 1, clients: [{ id: 2, name: 'Client', count: 1, invoices: [{ id: 4, number: 'INV-4', count: 1, kinds: { receipt: 1 } }], other: {} }] }]);
    expect(c[0]?.children[0]?.children[0]?.children[0]?.query).toEqual({ year: '2026', customer: '2', invoice: '4', kind: 'receipt' });
    const v = vendorFolders([{ year: 2026, count: 1, months: [{ month: 10, count: 1, vendors: [{ id: 3, name: 'Vendor', count: 1, kinds: { vendor_invoice: 1 } }] }] }]);
    expect(v[0]?.children[0]?.name).toBe('October'); expect(v[0]?.children[0]?.children[0]?.children[0]?.query.vendor).toBe('3');
  });
  it('blocks a client-only role from vendor files before fetching them', () => {
    const user = makeUser({ permissions: ['documents.client.view'] }); const calls = mockApi(common);
    renderWithAuth(<DocumentExplorer area="vendor" />, user);
    expect(screen.getByText('Access restricted')).toBeInTheDocument(); expect(calls.some(c => c.path.startsWith('/documents/'))).toBe(false);
  });
  it('does not offer restricted bank proof upload without evidence authority', async () => {
    mockApi({ ...common, '/documents/references/': { parties: [] } });
    renderWithAuth(<UploadDrawer area="client" onClose={vi.fn()} />, makeUser({ permissions: ['documents.client.view', 'documents.manage'] }));
    expect(screen.queryByRole('option', { name: 'Bank payment proof' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }));
    expect(await screen.findByText('Select a PDF, PNG, JPEG or WEBP file.')).toBeInTheDocument();
  });
  it('uploads multipart data with a CSRF token and a real financial link', async () => {
    const calls = mockApi({ ...common, '/documents/references/': { parties: [{ value: '2', label: 'Client' }], invoice_id: [{ value: '4', label: 'INV-4' }], payment_id: [] }, 'POST /documents/': { id: 11 } });
    const close = vi.fn(); renderWithAuth(<UploadDrawer area="client" initial={{ customer_id: '2', invoice_id: '4' }} onClose={close} />);
    await screen.findByRole('option', { name: 'INV-4' });
    await userEvent.upload(screen.getByLabelText('File'), new File(['test-content'], 'proof.pdf', { type: 'application/pdf' }));
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }));
    await waitFor(() => expect(close).toHaveBeenCalled());
    const call = calls.find(c => c.method === 'POST' && c.path === '/documents/');
    expect(call?.headers['X-CSRFToken']).toBe('test-token'); expect(call?.body).toBeInstanceOf(FormData);
    expect((call?.body as FormData).get('invoice_id')).toBe('4');
  });
  it('closes the document viewer with Escape and preserves private PDF access', async () => {
    const doc: FiledDocument = { id: 1, area: 'client', kind: 'invoice', title: 'Issued invoice', document_date: '2026-10-10', generated: true, restricted: false, customer_id: 1, customer_name: 'Client', vendor_id: null, vendor_name: null, invoice_id: 2, invoice_number: 'INV-2', payment_id: null, payment_number: null, receipt_id: null, credit_note_id: null, vendor_bill_id: null, bill_number: null, expense_id: null, expense_number: null, vendor_payment_id: null, notes: '', is_archived: false, archived_reason: '', archived_at: null, uploaded_by: null, created_at: '2026-10-10T12:00:00Z', content_type: 'application/pdf', size: 1000, file_name: 'official.pdf', sha256: 'abc', url: '/api/v1/files/private/content/', download_url: '/api/v1/files/private/content/?download=1' };
    const close = vi.fn(); renderWithAuth(<FileViewer doc={doc} onClose={close} />);
    expect(screen.getByTitle('Issued invoice')).toHaveAttribute('src', '/api/v1/files/private/content/#zoom=100');
    await userEvent.keyboard('{Escape}'); expect(close).toHaveBeenCalled();
  });
});

