'use client';
import Link from 'next/link';
import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Choice';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field } from '@/components/ui/Field';
import { Input, AmountInput, Select } from '@/components/ui/Input';
import { Drawer, DialogFooter, DialogActions, FormGrid, Cell } from '@/components/ui/Overlay';
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { useUnsavedGuard } from '@/lib/forms';
import { useAccounts } from '@/features/accounting/shared';
import type { Bank } from '@/features/accounting/types';
import { Screen } from '@/features/commerce/forms';
import { ListPanel, Primary, StatusBadge, LedgerImpact, DocumentBundle, METHODS, act, positive, sumDecimals, today, useActionKey, useApi, useMoney } from '@/features/commerce/shared';
import type { Bill, Expense, Vendor, VendorPayment, FiledDocument } from '@/features/commerce/types';
import { FileViewer } from '@/features/commerce/FileViewer';
import { UploadDrawer } from '@/features/filing/UploadDrawer';

interface Quote { base_currency: string; fx_difference: string; fx_account: string | null; quote_fingerprint: string; lines: { account_id: number; description: string; base_debit: string; base_credit: string }[] }
export function VendorPaymentDrawer({ vendorId, target, onClose }: { vendorId?: number; target?: { kind: 'bills' | 'expenses'; id: number; amount: string }; onClose: () => void }) {
  const vendors = useApi<Page<Vendor>>('/purchasing/vendors/?status=active&page_size=100'); const banks = useApi<Page<Bank>>('/banking/accounts/?page_size=100'); const accounts = useAccounts(); const money = useMoney(); const action = useActionKey();
  const [vendor, setVendor] = useState(String(vendorId ?? '')); const [bank, setBank] = useState(''); const [date, setDate] = useState(today()); const [method, setMethod] = useState('bank_transfer'); const [reference, setReference] = useState('');
  const [allocations, setAllocations] = useState<Record<string, string>>(target ? { [`${target.kind}/${target.id}`]: target.amount } : {});
  const bills = useApi<Page<Bill>>(vendor ? `/purchasing/bills/?vendor=${vendor}&status=open&page_size=100` : null); const expenses = useApi<Page<Expense>>(vendor ? `/purchasing/expenses/?vendor=${vendor}&mode=accrued&page_size=100` : null);
  const [quote, setQuote] = useState<Quote | null>(null); const [confirmFx, setConfirmFx] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null); const [discard, setDiscard] = useState(false);
  const selectedBank = banks.data?.results.find(b => String(b.id) === bank);
  const rows = [...(bills.data?.results ?? []).map(b => ({ id: `bills/${b.id}`, number: b.number, currency: b.currency, outstanding: b.outstanding })), ...(expenses.data?.results ?? []).filter(e => ['posted', 'partially_paid'].includes(e.status)).map(e => ({ id: `expenses/${e.id}`, number: e.number, currency: e.currency, outstanding: e.outstanding }))].filter(r => !selectedBank || r.currency === selectedBank.currency);
  const selected = rows.filter(r => positive(allocations[r.id]));
  const amount = sumDecimals(selected.map(r => allocations[r.id]));
  const data = { vendor_id: Number(vendor), bank_account_id: Number(bank), payment_date: date, amount, method, reference, allocations: selected.map(r => ({ [r.id.startsWith('bills/') ? 'bill_id' : 'expense_id']: Number(r.id.split('/')[1]), amount: allocations[r.id] })) };
  const dirty = Boolean(vendor || bank || reference || Object.keys(allocations).length); useUnsavedGuard(dirty);
  const changed = () => { setQuote(null); setConfirmFx(false); setError(null); };
  const close = () => { if (!busy) { if (dirty) setDiscard(true); else onClose(); } };
  const preview = async () => { if (busy) return; setBusy(true); setError(null); try { setQuote(await api.post<Quote>('/purchasing/payments/preview/', data)); } catch(e) { setError(errorMessage(e)); } finally { setBusy(false); } };
  const confirm = async () => { if (!quote || busy) return; setBusy(true); setError(null); try { await act(() => api.post<VendorPayment>('/purchasing/payments/', { ...data, posting_key: action.key, quote_fingerprint: quote.quote_fingerprint, confirm_fx: confirmFx }), p => p.status === 'paid' ? `Vendor payment ${p.number} posted` : `Vendor payment ${p.number} awaiting approval — not posted`); onClose(); } catch(e) { setError(errorMessage(e)); } finally { setBusy(false); } };
  return <><Drawer open title="Pay vendor" eyebrow="Purchases & Expenses" width={820} onClose={close} footer={<DialogFooter>{error && <Banner tone="err">{error}</Banner>}<DialogActions><Button disabled={busy} onClick={close}>Cancel</Button>{quote ? <Button variant="primary" disabled={busy || (positive(quote.fx_difference.replace('-', '')) && !confirmFx)} onClick={() => void confirm()}>{busy ? 'Posting…' : 'Confirm payment'}</Button> : <Button variant="primary" disabled={busy} onClick={() => void preview()}>{busy ? 'Calculating…' : 'Preview payment'}</Button>}</DialogActions></DialogFooter>}>
    <FormGrid>
      <Cell><Field label="Vendor" htmlFor="vp-vendor"><Select id="vp-vendor" value={vendor} onChange={e => { setVendor(e.target.value); setAllocations({}); changed(); }}><option value="">Select vendor…</option>{vendors.data?.results.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</Select></Field></Cell>
      <Cell><Field label="Paying account" htmlFor="vp-bank"><Select id="vp-bank" value={bank} onChange={e => { setBank(e.target.value); changed(); }}><option value="">Select account…</option>{banks.data?.results.filter(b => b.is_active).map(b => <option key={b.id} value={b.id}>{b.name} · {b.currency}</option>)}</Select></Field></Cell>
      <Cell><Field label="Payment date" htmlFor="vp-date"><Input id="vp-date" type="date" value={date} onChange={e => { setDate(e.target.value); changed(); }} /></Field></Cell>
      <Cell><Field label="Payment method" htmlFor="vp-method"><Select id="vp-method" value={method} onChange={e => { setMethod(e.target.value); changed(); }}>{METHODS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}</Select></Field></Cell>
      <Cell w="full"><Field label="Reference" htmlFor="vp-reference"><Input id="vp-reference" value={reference} onChange={e => { setReference(e.target.value); changed(); }} /></Field></Cell>
    </FormGrid>
    <div className="mt-4 border border-bd"><Table><THead><TR><TH>Open obligation</TH><TH align="right">Outstanding</TH><TH align="right">Allocate</TH></TR></THead><TBody>{rows.map(r => <TR key={r.id}><TD>{r.number}</TD><TD align="right">{money(r.outstanding, r.currency)}</TD><TD><AmountInput aria-label={`Allocate ${r.number}`} value={allocations[r.id] ?? ''} onChange={e => { setAllocations(v => ({ ...v, [r.id]: e.target.value })); changed(); }} /></TD></TR>)}{rows.length === 0 && <TR><TD colSpan={3}>{bills.loading || expenses.loading ? 'Loading open obligations…' : 'No open obligations for the selected vendor and account currency.'}</TD></TR>}</TBody></Table></div>
    <div className="my-3 text-right font-semibold">Payment total {money(amount, selectedBank?.currency)}</div>
    {quote && <div className="flex flex-col gap-3"><Banner tone="info">Reviewed preview · FX difference {money(quote.fx_difference, quote.base_currency)} {quote.fx_account ? `· ${quote.fx_account}` : ''}. Changed rates or carrying values require another preview.</Banner><Table><THead><TR><TH>Ledger account</TH><TH align="right">Debit</TH><TH align="right">Credit</TH></TR></THead><TBody>{quote.lines.map((l, i) => <TR key={i}><TD>{accounts.data?.find(a => a.id === l.account_id)?.name ?? l.description}</TD><TD align="right">{money(l.base_debit, quote.base_currency)}</TD><TD align="right">{money(l.base_credit, quote.base_currency)}</TD></TR>)}</TBody></Table>{positive(quote.fx_difference.replace('-', '')) && <Checkbox label="I reviewed and accept the disclosed FX difference" checked={confirmFx} onChange={setConfirmFx} />}</div>}
  </Drawer><ConfirmDialog open={discard} title="Discard unsaved payment?" confirmLabel="Discard" danger onCancel={() => setDiscard(false)} onConfirm={onClose} /></>;
}
export function VendorPaymentsPage() {
  const { can } = useAuth(); const money = useMoney(); const [create, setCreate] = useState(false);
  return <Screen eyebrow="Purchases & Expenses" title="Vendor payments" description="Settlements of posted bills and accrued expenses, with explicit allocation and FX review." actions={can('vendor_payments.manage') && <Button variant="primary" icon="payments" onClick={() => setCreate(true)}>Pay vendor</Button>}>
    <ListPanel<VendorPayment> path="/purchasing/payments/" columns={[
      { key: 'no', label: 'Payment', render: p => <Primary href={`/purchases/payments/${p.id}`} mono title={p.number} sub={p.reference} /> }, { key: 'vendor', label: 'Vendor', render: p => p.vendor_name }, { key: 'date', label: 'Date', render: p => formatDate(p.payment_date) }, { key: 'account', label: 'Account', render: p => p.bank_account_name }, { key: 'status', label: 'Status', render: p => <StatusBadge status={p.status} /> }, { key: 'amount', label: 'Amount', align: 'right', render: p => money(p.amount, p.currency) },
    ]} />{create && <VendorPaymentDrawer onClose={() => setCreate(false)} />}
  </Screen>;
}
export function VendorPaymentDetail({ id }: { id: string }) {
  const query = useApi<VendorPayment>(`/purchasing/payments/${id}/`); const p = query.data; const { can } = useAuth(); const money = useMoney(); const [reverse, setReverse] = useState(false); const [upload, setUpload] = useState(false); const [view, setView] = useState<FiledDocument | null>(null);
  return <Screen eyebrow="Vendor payment" title={p?.number ?? 'Vendor payment'} description={p ? `${p.vendor_name} · ${money(p.amount, p.currency)} · ${p.status}` : ''} actions={p?.status === 'paid' && can('vendor_payments.manage') && <Button variant="danger" onClick={() => setReverse(true)}>Reverse payment</Button>}>
    {Boolean(query.error) && <Banner tone="err">{errorMessage(query.error)}</Banner>}
    {p && <><Table><THead><TR><TH>Allocated document</TH><TH align="right">Amount</TH></TR></THead><TBody>{p.allocations.map((a, i) => <TR key={i}><TD><Link href={`/purchases/${a.bill_id ? 'bills' : 'expenses'}/${a.bill_id ?? a.expense_id}`}>{a.document}</Link></TD><TD align="right">{money(a.amount, p.currency)}</TD></TR>)}</TBody></Table><LedgerImpact journals={[p.journal, p.reversal_journal]} empty="Pending approvals have no posted payment effect." /><DocumentBundle query={`area=vendor&vendor_payment=${p.id}`} empty="No vendor payment receipt attached." onOpen={setView} actions={can('documents.manage') && <Button size="sm" onClick={() => setUpload(true)}>Upload payment receipt</Button>} />{upload && <UploadDrawer area="vendor" initial={{ kind: 'vendor_receipt', vendor_id: String(p.vendor_id), vendor_payment_id: String(p.id) }} onClose={() => setUpload(false)} />}</>}
    <ConfirmDialog open={reverse} title="Reverse vendor payment?" confirmLabel="Reverse payment" reason="required" danger onCancel={() => setReverse(false)} onConfirm={async reason => { await act(() => api.post(`/purchasing/payments/${id}/reverse/`, { reason }), 'Vendor payment reversed'); setReverse(false); }}>Original payment evidence is retained. Allocated obligations reopen only after a successful linked reversal.</ConfirmDialog>
    {view && <FileViewer doc={view} onClose={() => setView(null)} />}
  </Screen>;
}
