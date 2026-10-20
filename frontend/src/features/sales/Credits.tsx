'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Segmented } from '@/components/ui/Choice';
import { Field } from '@/components/ui/Field';
import { AmountInput, Input, Select, Textarea } from '@/components/ui/Input';
import { Cell, DialogActions, DialogFooter, Drawer, FormGrid } from '@/components/ui/Overlay';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';

import type { Bank } from '@/features/accounting/types';
import { Screen } from '@/features/commerce/forms';
import {
  ListPanel,
  METHODS,
  PdfState,
  Primary,
  StatusBadge,
  act,
  positive,
  sumDecimals,
  today,
  trimDecimal,
  useActionKey,
  useApi,
  useMoney,
} from '@/features/commerce/shared';
import type { CreditNote, Invoice, InvoiceRow, Refund } from '@/features/commerce/types';

const EYEBROW = 'Sales & Billing';

function remaining(line: Invoice['lines'][number]) {
  return sumDecimals([line.taxable, line.tax, `-${line.credited_taxable ?? '0'}`, `-${line.credited_tax ?? '0'}`]);
}

export function CreditNoteDrawer({ invoice, onClose }: { invoice: Invoice; onClose: () => void }) {
  const money = useMoney();
  const { key } = useActionKey();
  const [mode, setMode] = useState<'full' | 'lines'>('lines');
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [reason, setReason] = useState('');
  const [date, setDate] = useState(today());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cur = invoice.currency;
  const total = mode === 'full' ? sumDecimals(invoice.lines.map(remaining)) : sumDecimals(Object.values(amounts));
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await act(
        () =>
          api.post<CreditNote>(`/billing/invoices/${invoice.id}/credit-notes/`, {
            posting_key: key,
            reason,
            issue_date: date,
            full: mode === 'full',
            lines:
              mode === 'lines'
                ? Object.entries(amounts)
                    .filter(([, v]) => positive(v))
                    .map(([id, amount]) => ({ invoice_line_id: Number(id), amount }))
                : [],
          }),
        (note) => ((note as CreditNote).status === 'issued' ? `Credit note ${(note as CreditNote).number} issued` : 'Credit note submitted for approval'),
      );
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer
      open
      title={`Credit ${invoice.number}`}
      eyebrow="Credit note"
      description="The original invoice is never edited. The credit reverses revenue and tax; it reduces the open balance, and any excess over the open balance becomes customer credit."
      width={720}
      onClose={() => !busy && onClose()}
      footer={
        <DialogFooter>
          {error && <Banner tone="err">{error}</Banner>}
          <DialogActions>
            <Button disabled={busy} onClick={onClose}>
              Cancel
            </Button>
            <Button variant="primary" disabled={busy || !reason.trim() || !positive(total)} onClick={() => void submit()}>
              {busy ? 'Issuing…' : `Issue credit of ${money(total, cur)}`}
            </Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      <FormGrid>
        <Cell w="full">
          <Segmented label="Credit scope" value={mode} onChange={setMode} options={[{ value: 'lines', label: 'Partial (by line)' }, { value: 'full', label: 'Everything still creditable' }]} />
        </Cell>
        <Cell w="full">
          <div className="border border-bd">
            <div className="grid grid-cols-[minmax(0,1fr)_130px_130px] border-b border-bd bg-sf2 px-3 py-2 text-[10.5px] font-semibold uppercase tracking-[.07em] text-tx3">
              <span>Line</span>
              <span className="text-right">Creditable</span>
              <span className="text-right">Credit (incl. tax)</span>
            </div>
            {invoice.lines.map((line) => (
              <div key={line.id} className="grid grid-cols-[minmax(0,1fr)_130px_130px] items-center gap-2 border-b border-bd px-3 py-2 text-[12.5px] last:border-b-0">
                <span className="truncate">{line.description}</span>
                <span className="text-right tabular-nums text-tx2">{money(remaining(line), cur)}</span>
                {mode === 'lines' ? (
                  <AmountInput controlSize="sm" aria-label={`Credit for ${line.description}`} value={amounts[line.id!] ?? ''} onChange={(e) => setAmounts({ ...amounts, [line.id!]: e.target.value })} />
                ) : (
                  <span className="text-right tabular-nums">{money(remaining(line), cur)}</span>
                )}
              </div>
            ))}
          </div>
        </Cell>
        <Cell w="third">
          <Field label="Credit note date" htmlFor="cn-date">
            <Input id="cn-date" type="date" aria-label="Credit note date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
        </Cell>
        <Cell w="twothird">
          <Field label="Reason" htmlFor="cn-reason" required>
            <Input id="cn-reason" aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </Cell>
      </FormGrid>
    </Drawer>
  );
}

export function RefundDrawer({ onClose }: { onClose: () => void }) {
  const money = useMoney();
  const { key } = useActionKey();
  const customers = useApi<Page<{ id: number; name: string; currency: string }>>('/sales/customers/?page_size=100');
  const banks = useApi<Page<Bank>>('/banking/accounts/?page_size=100');
  const [customerId, setCustomerId] = useState('');
  const account = useApi<{ credit: { currency: string; amount: string }[] }>(customerId ? `/billing/customers/${customerId}/account/` : null);
  const [bankId, setBankId] = useState('');
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('bank_transfer');
  const [reference, setReference] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const credits = account.data?.credit ?? [];
  const bank = banks.data?.results.find((b) => String(b.id) === bankId);
  const available = credits.find((c) => c.currency === bank?.currency);
  return (
    <Drawer
      open
      title="Refund customer credit"
      eyebrow="Refund"
      description="A refund returns actual money from a bank or cash account and uses up customer credit. It never edits an invoice."
      width={600}
      onClose={() => !busy && onClose()}
      footer={
        <DialogFooter>
          {error && <Banner tone="err">{error}</Banner>}
          <DialogActions>
            <Button disabled={busy} onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={busy || !customerId || !bankId || !amount || !reason.trim()}
              onClick={async () => {
                setBusy(true);
                setError(null);
                try {
                  await act(
                    () => api.post<Refund>('/billing/refunds/', { posting_key: key, customer_id: Number(customerId), bank_account_id: Number(bankId), amount, method, reference, reason, refund_date: today() }),
                    (r) => ((r as Refund).status === 'paid' ? `Refund ${(r as Refund).number} paid` : 'Refund submitted for approval'),
                  );
                  onClose();
                } catch (e) {
                  setError(errorMessage(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? 'Paying…' : 'Pay refund'}
            </Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      <FormGrid>
        <Cell w="full">
          <Field label="Customer" htmlFor="rf-customer" required>
            <Select id="rf-customer" aria-label="Customer" value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
              <option value="">Select customer</option>
              {customers.data?.results.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
        </Cell>
        {customerId && (
          <Cell w="full">
            <Banner tone={credits.length ? 'info' : 'warn'}>
              {credits.length ? `Available customer credit: ${credits.map((c) => money(c.amount, c.currency)).join(', ')}` : 'This customer has no credit to refund.'}
            </Banner>
          </Cell>
        )}
        <Cell w="half">
          <Field label="Paying account" htmlFor="rf-bank" required>
            <Select id="rf-bank" aria-label="Paying account" value={bankId} onChange={(e) => setBankId(e.target.value)}>
              <option value="">Select account</option>
              {banks.data?.results.filter((b) => b.is_active).map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} · {b.currency}
                </option>
              ))}
            </Select>
          </Field>
        </Cell>
        <Cell w="half">
          <Field label="Amount" htmlFor="rf-amount" required hint={available ? `Up to ${money(available.amount, available.currency)}` : undefined}>
            <AmountInput id="rf-amount" aria-label="Refund amount" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
        </Cell>
        <Cell w="half">
          <Field label="Method" htmlFor="rf-method">
            <Select id="rf-method" aria-label="Method" value={method} onChange={(e) => setMethod(e.target.value)}>
              {METHODS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>
        </Cell>
        <Cell w="half">
          <Field label="Reference" htmlFor="rf-ref">
            <Input id="rf-ref" aria-label="Reference" value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
        </Cell>
        <Cell w="full">
          <Field label="Reason" htmlFor="rf-reason" required>
            <Textarea id="rf-reason" aria-label="Reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </Cell>
      </FormGrid>
    </Drawer>
  );
}

export function ApplyCreditDrawer({ onClose }: { onClose: () => void }) {
  const money = useMoney();
  const { key } = useActionKey();
  const customers = useApi<Page<{ id: number; name: string }>>('/sales/customers/?page_size=100');
  const [customerId, setCustomerId] = useState('');
  const account = useApi<{ credit: { currency: string; amount: string }[] }>(customerId ? `/billing/customers/${customerId}/account/` : null);
  const invoices = useApi<Page<InvoiceRow>>(customerId ? `/billing/invoices/?customer=${customerId}&status=open&page_size=100` : null);
  const [invoiceId, setInvoiceId] = useState('');
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const invoice = invoices.data?.results.find((i) => String(i.id) === invoiceId);
  const credit = account.data?.credit.find((c) => c.currency === invoice?.currency);
  return (
    <Drawer
      open
      title="Apply customer credit"
      eyebrow="Customer credit"
      description="Settles an open invoice from the customer's credit balance (unapplied receipts or excess credit notes)."
      width={560}
      onClose={() => !busy && onClose()}
      footer={
        <DialogFooter>
          {error && <Banner tone="err">{error}</Banner>}
          <DialogActions>
            <Button disabled={busy} onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={busy || !invoiceId || !amount}
              onClick={async () => {
                setBusy(true);
                setError(null);
                try {
                  await act(() => api.post('/billing/credit-applications/', { posting_key: key, invoice_id: Number(invoiceId), amount }), 'Customer credit applied');
                  onClose();
                } catch (e) {
                  setError(errorMessage(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Apply credit
            </Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      <FormGrid>
        <Cell w="full">
          <Field label="Customer" htmlFor="ap-customer" required>
            <Select id="ap-customer" aria-label="Customer" value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
              <option value="">Select customer</option>
              {customers.data?.results.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
        </Cell>
        <Cell w="full">
          <Field label="Open invoice" htmlFor="ap-invoice" required>
            <Select id="ap-invoice" aria-label="Open invoice" value={invoiceId} onChange={(e) => { setInvoiceId(e.target.value); const inv = invoices.data?.results.find((i) => String(i.id) === e.target.value); if (inv) setAmount(trimDecimal(inv.outstanding)); }}>
              <option value="">Select invoice</option>
              {invoices.data?.results.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.number} · {money(i.outstanding, i.currency)} open
                </option>
              ))}
            </Select>
          </Field>
        </Cell>
        <Cell w="full">
          <Field label="Amount" htmlFor="ap-amount" required hint={credit ? `Available credit ${money(credit.amount, credit.currency)}` : invoice ? `No ${invoice.currency} credit available` : undefined}>
            <AmountInput id="ap-amount" aria-label="Amount to apply" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
        </Cell>
      </FormGrid>
    </Drawer>
  );
}

export function CreditsPage() {
  const { can } = useAuth();
  const money = useMoney();
  const [drawer, setDrawer] = useState<'refund' | 'apply' | null>(null);
  return (
    <Screen
      eyebrow={EYEBROW}
      title="Credit notes & refunds"
      description="Corrections to issued invoices. The original invoice is never edited — credit notes reduce the receivable and refunds return cash when credit exceeds the balance. Open an invoice to credit it."
      actions={
        <>
          {can('payments.record') && (
            <Button icon="playlist_add_check" onClick={() => setDrawer('apply')}>
              Apply customer credit
            </Button>
          )}
          {can('credit_notes.manage') && (
            <Button variant="primary" icon="currency_exchange" onClick={() => setDrawer('refund')}>
              Refund credit
            </Button>
          )}
        </>
      }
    >
      <ListPanel<CreditNote>
        path="/billing/credit-notes/"
        title="Credit notes"
        search="Search credit notes…"
        empty="No credit notes. Open an issued invoice and choose Credit note."
        columns={[
          { key: 'no', label: 'Credit note', render: (x) => <Primary mono title={x.number ?? 'Awaiting approval'} /> },
          { key: 'date', label: 'Date', render: (x) => formatDate(x.issue_date) },
          {
            key: 'inv',
            label: 'Invoice',
            render: (x) => (
              <Link href={`/sales/invoices/${x.invoice_id}`} className="font-mono text-[12.5px]">
                {x.invoice_number}
              </Link>
            ),
          },
          { key: 'cu', label: 'Customer', render: (x) => x.customer_name },
          { key: 'reason', label: 'Reason', render: (x) => x.reason },
          { key: 'st', label: 'Status', render: (x) => <StatusBadge status={x.status} /> },
          {
            key: 'amt',
            label: 'Credit',
            align: 'right',
            render: (x) => (
              <div className="flex flex-col items-end">
                <span className="font-semibold">{money(x.total, x.currency)}</span>
                {positive(x.credit_amount) && <span className="text-[11.5px] text-tx3">{money(x.credit_amount, x.currency)} to customer credit</span>}
              </div>
            ),
          },
          {
            key: 'pdf',
            label: 'PDF',
            render: (x) =>
              x.number ? (
                <PdfState status={x.pdf_status} url={x.pdf_url} error={x.pdf_error} canRetry={can('credit_notes.manage')} onRetry={() => api.post(`/billing/credit-notes/${x.id}/pdf/`)} />
              ) : (
                <span className="text-tx3">—</span>
              ),
          },
        ]}
      />
      <ListPanel<Refund>
        path="/billing/refunds/"
        title="Refunds"
        search="Search refunds…"
        empty="No refunds paid."
        columns={[
          { key: 'no', label: 'Refund', render: (x) => <Primary mono title={x.number} /> },
          { key: 'date', label: 'Date', render: (x) => formatDate(x.refund_date) },
          { key: 'cu', label: 'Customer', render: (x) => x.customer_name },
          { key: 'bank', label: 'Paid from', render: (x) => x.bank_account_name },
          { key: 'reason', label: 'Reason', render: (x) => x.reason },
          { key: 'st', label: 'Status', render: (x) => <StatusBadge status={x.status} /> },
          { key: 'amt', label: 'Amount', align: 'right', render: (x) => <span className="font-semibold">{money(x.amount, x.currency)}</span> },
        ]}
      />
      {drawer === 'refund' && <RefundDrawer onClose={() => setDrawer(null)} />}
      {drawer === 'apply' && <ApplyCreditDrawer onClose={() => setDrawer(null)} />}
    </Screen>
  );
}
