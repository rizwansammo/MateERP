'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Choice';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field } from '@/components/ui/Field';
import { Icon } from '@/components/ui/Icon';
import { InfoPanel, InfoPanels } from '@/components/ui/InfoPanel';
import { AmountInput, Input, Select, Textarea } from '@/components/ui/Input';
import { Cell, DialogActions, DialogFooter, Drawer, FormGrid, FormSection } from '@/components/ui/Overlay';
import { toast } from '@/components/ui/Toast';
import { api, ApiError, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate, formatDateTime } from '@/lib/format';
import { useUnsavedGuard } from '@/lib/forms';

import type { Bank } from '@/features/accounting/types';
import { Screen } from '@/features/commerce/forms';
import { FileViewer } from '@/features/commerce/FileViewer';
import {
  DocumentBundle,
  LedgerImpact,
  METHODS,
  act,
  methodLabel,
  positive,
  refreshCommerce,
  statusLabel,
  sumDecimals,
  today,
  trimDecimal,
  useActionKey,
  useApi,
  useMoney,
} from '@/features/commerce/shared';
import type { FiledDocument, Invoice, InvoiceRow, Payment, Receipt } from '@/features/commerce/types';

import { ReceiptPaper } from './preview';
import { PaymentTable } from './tables';

const EYEBROW = 'Sales & Billing';

export function PaymentsPage() {
  const { can } = useAuth();
  const [record, setRecord] = useState(false);
  return (
    <Screen
      eyebrow={EYEBROW}
      title="Payments"
      description="Client payments are verified before they reduce the invoice balance. Each verified payment receives its own official money receipt."
      actions={
        can('payments.record') && (
          <Button variant="primary" icon="payments" onClick={() => setRecord(true)}>
            Record payment
          </Button>
        )
      }
    >
      <PaymentTable filters />
      {record && <RecordPaymentDrawer onClose={() => setRecord(false)} />}
    </Screen>
  );
}

interface Row {
  invoice_id: string;
  amount: string;
}

/** Record a received payment. It has no ledger effect until a different user verifies it. */
export function RecordPaymentDrawer({ invoice, onClose }: { invoice?: Invoice | InvoiceRow; onClose: () => void }) {
  const { can } = useAuth();
  const money = useMoney();
  const router = useRouter();
  const { key } = useActionKey();
  const banks = useApi<Page<Bank>>('/banking/accounts/?page_size=100');
  const [customerId, setCustomerId] = useState(invoice ? String(invoice.customer_id) : '');
  const customers = useApi<Page<{ id: number; name: string; currency: string }>>(invoice ? null : '/sales/customers/?status=active&page_size=100');
  const openInvoices = useApi<Page<InvoiceRow>>(customerId ? `/billing/invoices/?customer=${customerId}&status=open&page_size=100` : null);
  const [rows, setRows] = useState<Row[]>(invoice ? [{ invoice_id: String(invoice.id), amount: trimDecimal(invoice.outstanding) }] : []);
  const [amount, setAmount] = useState(invoice ? trimDecimal(invoice.outstanding) : '');
  const [bankId, setBankId] = useState('');
  const [date, setDate] = useState(today());
  const [method, setMethod] = useState('bank_transfer');
  const [reference, setReference] = useState('');
  const [notes, setNotes] = useState('');
  const [acceptUnapplied, setAcceptUnapplied] = useState(false);
  const [proof, setProof] = useState<File | null>(null);
  const [discard, setDiscard] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const currency = invoice?.currency ?? openInvoices.data?.results[0]?.currency ?? customers.data?.results.find((c) => String(c.id) === customerId)?.currency ?? '';
  const eligibleBanks = (banks.data?.results ?? []).filter((b) => b.is_active && (!currency || b.currency === currency));
  const bank = bankId || (eligibleBanks.length === 1 ? String(eligibleBanks[0]!.id) : '');
  const allocated = sumDecimals(rows.map((r) => r.amount || '0'));
  const remainder = sumDecimals([amount || '0', `-${allocated}`]);
  const canProof = can('documents.manage') && can('banking.evidence.view');
  const signature = JSON.stringify([customerId, rows, amount, bankId, date, method, reference, notes, acceptUnapplied]);
  const [initialSignature] = useState(signature);
  const dirty = signature !== initialSignature || Boolean(proof);
  useUnsavedGuard(dirty && !busy);
  const close = () => { if (!busy) { if (dirty) setDiscard(true); else onClose(); } };

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const payment = await api.post<Payment>('/billing/payments/', {
        posting_key: key,
        customer_id: Number(customerId),
        bank_account_id: Number(bank),
        payment_date: date,
        amount,
        method,
        reference,
        notes,
        accept_unapplied: acceptUnapplied,
        allocations: rows.filter((r) => r.invoice_id && r.amount).map((r) => ({ invoice_id: Number(r.invoice_id), amount: r.amount })),
      });
      if (proof) {
        const form = new FormData();
        form.append('kind', 'bank_proof');
        form.append('file', proof);
        form.append('customer_id', customerId);
        form.append('payment_id', String(payment.id));
        if (rows.length === 1 && rows[0]?.invoice_id) form.append('invoice_id', rows[0].invoice_id);
        form.append('document_date', date);
        form.append('title', `Bank payment proof — ${payment.number}`);
        try {
          await api.post('/documents/', form);
        } catch (e) {
          toast(`Payment recorded, but the proof was not filed: ${errorMessage(e)}`, 'warn');
        }
      }
      refreshCommerce();
      toast(`Payment ${payment.number} recorded — pending verification`);
      onClose();
      router.push(`/sales/payments/${payment.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? Object.values(e.fieldErrors())[0] ?? e.message : errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <><Drawer
      open
      title="Record payment"
      eyebrow="Client payment"
      description="Recording has no accounting effect. A different user verifies the funds before the receivable is reduced and the money receipt is issued."
      width={720}
      onClose={close}
      footer={
        <DialogFooter>
          {error && <Banner tone="err">{error}</Banner>}
          <DialogActions>
            <Button disabled={busy} onClick={close}>
              Cancel
            </Button>
            <Button variant="primary" disabled={busy || !customerId || !bank || !amount} onClick={() => void submit()}>
              {busy ? 'Recording…' : 'Record for verification'}
            </Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      <FormGrid>
        {!invoice && (
          <Cell w="full">
            <Field label="Customer" htmlFor="pay-customer" required>
              <Select id="pay-customer" aria-label="Customer" value={customerId} onChange={(e) => { setCustomerId(e.target.value); setRows([]); }}>
                <option value="">Select customer</option>
                {customers.data?.results.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · {c.currency}
                  </option>
                ))}
              </Select>
            </Field>
          </Cell>
        )}
        <Cell w="third">
          <Field label={`Amount received${currency ? ` (${currency})` : ''}`} htmlFor="pay-amount" required>
            <AmountInput id="pay-amount" aria-label="Amount received" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
        </Cell>
        <Cell w="third">
          <Field label="Payment date" htmlFor="pay-date" required>
            <Input id="pay-date" type="date" aria-label="Payment date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} />
          </Field>
        </Cell>
        <Cell w="third">
          <Field label="Payment method" htmlFor="pay-method">
            <Select id="pay-method" aria-label="Payment method" value={method} onChange={(e) => setMethod(e.target.value)}>
              {METHODS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>
        </Cell>
        <Cell w="half">
          <Field label="Receiving bank / cash account" htmlFor="pay-bank" required hint={currency ? `Only ${currency} accounts can receive this payment.` : undefined}>
            <Select id="pay-bank" aria-label="Receiving account" value={bank} onChange={(e) => setBankId(e.target.value)}>
              <option value="">Select account</option>
              {eligibleBanks.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} · {b.currency}
                </option>
              ))}
            </Select>
          </Field>
        </Cell>
        <Cell w="half">
          <Field label="Transaction reference" htmlFor="pay-ref">
            <Input id="pay-ref" aria-label="Transaction reference" value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
        </Cell>
        <FormSection title="Allocation to invoices" />
        <Cell w="full">
          <div className="flex flex-col border border-bd">
            {rows.map((r, i) => {
              const inv = openInvoices.data?.results.find((x) => String(x.id) === r.invoice_id) ?? (invoice && String(invoice.id) === r.invoice_id ? invoice : undefined);
              return (
                <div key={i} className="grid grid-cols-[minmax(0,1fr)_150px_34px] items-center gap-2 border-b border-bd px-3 py-2 last:border-b-0">
                  <Select controlSize="sm" aria-label={`Allocation ${i + 1} invoice`} value={r.invoice_id} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, invoice_id: e.target.value } : x)))}>
                    <option value="">Select invoice</option>
                    {(openInvoices.data?.results ?? (invoice ? [invoice as InvoiceRow] : [])).map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.number} · {money(x.outstanding, x.currency)} open
                      </option>
                    ))}
                  </Select>
                  <AmountInput controlSize="sm" aria-label={`Allocation ${i + 1} amount`} value={r.amount} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))} />
                  <button type="button" aria-label={`Remove allocation ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))} className="flex size-7 items-center justify-center bg-transparent text-tx3 hover:text-err">
                    <Icon name="close" size={16} />
                  </button>
                  {inv && <span className="col-span-3 text-[11px] text-tx3">Due {formatDate(inv.due_date)} · total {money(inv.total, inv.currency)}</span>}
                </div>
              );
            })}
            <div className="flex items-center justify-between gap-2 px-3 py-2 text-[12px]">
              <Button size="xs" icon="add" disabled={!customerId} onClick={() => setRows([...rows, { invoice_id: '', amount: '' }])}>
                Add invoice
              </Button>
              <span className="text-tx3">
                Allocated {money(allocated, currency || undefined)} · Unallocated <b className={positive(remainder) ? 'text-warn' : 'text-tx'}>{money(remainder, currency || undefined)}</b>
              </span>
            </div>
          </div>
        </Cell>
        {positive(remainder) && (
          <Cell w="full">
            <Checkbox
              checked={acceptUnapplied}
              onChange={setAcceptUnapplied}
              label="Hold the unallocated amount as customer credit"
              hint="On verification it is posted to the customer-credit control account and can later be applied to invoices or refunded."
            />
          </Cell>
        )}
        <Cell w="full">
          <Field label="Notes" htmlFor="pay-notes">
            <Textarea id="pay-notes" aria-label="Notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
        </Cell>
        <FormSection title="Bank payment evidence (internal — not sent to the client)" />
        <Cell w="full">
          {canProof ? (
            <label className="flex cursor-pointer items-center gap-3 border border-dashed border-bd2 bg-sf2 px-3.5 py-3 text-[12.5px] text-tx2">
              <Icon name="upload_file" size={20} className="text-tx3" />
              <span className="flex-1">{proof ? proof.name : 'Attach the bank credit confirmation (PDF, PNG, JPEG or WEBP, up to 10 MB)'}</span>
              <input type="file" accept="application/pdf,image/png,image/jpeg,image/webp" className="sr-only" aria-label="Bank payment proof" onChange={(e) => setProof(e.target.files?.[0] ?? null)} />
            </label>
          ) : (
            <p className="m-0 text-[12px] text-tx3">Filing bank evidence requires document management and banking-evidence access.</p>
          )}
        </Cell>
      </FormGrid>
    </Drawer>
    <ConfirmDialog open={discard} title="Discard unsaved payment?" confirmLabel="Discard" danger onCancel={() => setDiscard(false)} onConfirm={onClose} /></>
  );
}

export function PaymentDetail({ id }: { id: string }) {
  const { can, user } = useAuth();
  const money = useMoney();
  const query = useApi<Payment>(`/billing/payments/${id}/`);
  const receipt = useApi<Receipt>(
    query.data?.receipt ? `/billing/receipts/${query.data.receipt.id}/` : null,
  );
  const [decision, setDecision] = useState<'verify' | 'reject' | 'cancel' | 'reverse' | null>(null);
  const [checked, setChecked] = useState(false);
  const [viewing, setViewing] = useState<FiledDocument | null>(null);
  const p = query.data;
  if (!p) return <Screen eyebrow="Client payment" title={query.error ? 'Payment not found' : 'Loading…'} />;
  const pending = p.status === 'pending_verification';
  const own = user?.id === p.recorded_by_id;
  return (
    <Screen
      eyebrow={`Client payment · ${statusLabel(p.status)}`}
      title={`${p.number} — ${money(p.amount, p.currency)}`}
      description={`${p.customer_name} · ${p.allocations.map((a) => a.invoice_number).join(', ') || 'Unallocated'} · ${formatDate(p.payment_date)} · ${methodLabel(p.method)}`}
      actions={
        <>
          {p.allocations[0] && (
            <Link href={`/sales/invoices/${p.allocations[0].invoice_id}`} className="inline-flex h-[34px] items-center gap-1.5 border border-bd2 bg-sf px-[14px] text-[12.5px] font-medium text-tx hover:no-underline">
              <Icon name="description" size={17} /> Invoice
            </Link>
          )}
          {pending && can('payments.record') && (
            <Button variant="danger" onClick={() => setDecision('cancel')}>
              Cancel
            </Button>
          )}
          {pending && can('payments.approve') && !own && (
            <>
              <Button variant="danger" onClick={() => setDecision('reject')}>
                Reject
              </Button>
              <Button variant="primary" icon="fact_check" onClick={() => setDecision('verify')}>
                Verify payment
              </Button>
            </>
          )}
          {p.status === 'verified' && can('payments.approve') && (
            <Button variant="danger" icon="undo" onClick={() => setDecision('reverse')}>
              Reverse
            </Button>
          )}
        </>
      }
    >
      {pending && own && can('payments.approve') && (
        <Banner tone="warn">You recorded this payment, so a different user must verify it (segregation of duties).</Banner>
      )}
      {p.status === 'awaiting_approval' && <Banner tone="warn">Verification is waiting for approval under the client-payments policy.</Banner>}
      {p.status === 'rejected' && <Banner tone="err">Rejected — {p.decision_reason}</Banner>}
      {p.status === 'reversed' && <Banner tone="neutral">Reversed — {p.decision_reason}. The receipt is marked cancelled; the original PDF stays on record.</Banner>}
      <InfoPanels>
        <InfoPanel
          title="Payment details"
          rows={[
            { label: 'Amount', value: money(p.amount, p.currency), strong: true },
            ...(p.base_amount ? [{ label: 'Base equivalent', value: money(p.base_amount) }] : []),
            { label: 'Received into', value: p.bank_account_name },
            { label: 'Reference', value: p.reference },
            { label: 'Unallocated (customer credit)', value: positive(p.unapplied_amount) ? money(p.unapplied_amount, p.currency) : '' },
            { label: 'Notes', value: p.notes },
          ]}
        />
        <InfoPanel
          title="Verification"
          rows={[
            { label: 'Status', value: statusLabel(p.status) },
            { label: 'Recorded by', value: `${p.recorded_by} · ${formatDateTime(p.recorded_at)}` },
            { label: 'Decided by', value: p.decided_by ? `${p.decided_by} · ${formatDateTime(p.decided_at)}` : '' },
            { label: 'Money receipt', value: p.receipt ? `${p.receipt.number}${p.receipt.status === 'cancelled' ? ' (cancelled)' : ''}` : '' },
          ]}
        />
        <InfoPanel title="Allocation" rows={p.allocations.map((a) => ({ label: a.invoice_number, value: money(a.amount, p.currency) }))} />
      </InfoPanels>
      {receipt.data && (
        <div className="grid items-start gap-[18px]" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 480px), 1fr))' }}>
          <section className="border border-bd bg-sf">
            <header className="flex items-center justify-between gap-2 border-b border-bd px-4 py-3">
              <div>
                <h2 className="m-0 text-[13px] font-semibold">Official money receipt</h2>
                <div className="text-[11.5px] text-tx3">Snapshot · branding version {receipt.data.branding_version} · immutable</div>
              </div>
              {receipt.data.pdf_url && (
                <a href={receipt.data.pdf_url} target="_blank" rel="noreferrer" className="inline-flex h-[28px] items-center gap-[5px] border border-bd2 bg-sf px-2.5 text-[12px] font-medium text-tx hover:no-underline">
                  <Icon name="picture_as_pdf" size={16} /> PDF
                </a>
              )}
            </header>
            <div className="flex justify-center overflow-hidden bg-sf3 p-[18px]">
              <ReceiptPaper snapshot={receipt.data.snapshot} number={receipt.data.number} version={receipt.data.branding_version} scale={0.6} />
            </div>
          </section>
          <div className="flex min-w-0 flex-col gap-[18px]">
            <LedgerImpact journals={[p.journal, p.reversal_journal]} empty="" />
          </div>
        </div>
      )}
      {!receipt.data && <LedgerImpact journals={[p.journal]} empty="Recorded payments have no ledger effect until they are verified." />}
      <DocumentBundle query={`payment=${p.id}`} title="Payment evidence" empty="No evidence filed. Bank proofs are visible only to users with banking-evidence access." onOpen={setViewing} />
      <ConfirmDialog
        open={decision === 'verify'}
        title={`Verify ${p.number}?`}
        confirmLabel="Verify & post"
        onCancel={() => setDecision(null)}
        onConfirm={async () => {
          if (!checked) throw new Error('Confirm that the funds were received before verifying.');
          await act(() => api.post(`/billing/payments/${p.id}/verify/`), (r: unknown) => ((r as Payment).status === 'awaiting_approval' ? 'Submitted for approval' : 'Payment verified — money receipt issued'));
          setDecision(null);
        }}
      >
        <p className="m-0">
          Posting debits {p.bank_account_name} and credits accounts receivable{positive(p.unapplied_amount) ? ' and customer credit' : ''}. Revenue was recognised when the invoice was issued.
        </p>
        <Checkbox checked={checked} onChange={setChecked} label={`I confirm ${money(p.amount, p.currency)} was received in ${p.bank_account_name}`} />
      </ConfirmDialog>
      <ConfirmDialog open={decision === 'reject'} title={`Reject ${p.number}?`} confirmLabel="Reject" danger reason="required" onCancel={() => setDecision(null)} onConfirm={async (reason) => { await act(() => api.post(`/billing/payments/${p.id}/reject/`, { reason }), 'Payment rejected'); setDecision(null); }}>
        Rejected payments keep their record and never affect the ledger.
      </ConfirmDialog>
      <ConfirmDialog open={decision === 'cancel'} title={`Cancel ${p.number}?`} confirmLabel="Cancel payment" danger reason="optional" onCancel={() => setDecision(null)} onConfirm={async (reason) => { await act(() => api.post(`/billing/payments/${p.id}/cancel/`, { reason }), 'Payment cancelled'); setDecision(null); }}>
        Use this when the payment was recorded in error. It has no ledger effect.
      </ConfirmDialog>
      <ConfirmDialog open={decision === 'reverse'} title={`Reverse ${p.number}?`} confirmLabel="Reverse payment" danger reason="required" onCancel={() => setDecision(null)} onConfirm={async (reason) => { await act(() => api.post(`/billing/payments/${p.id}/reverse/`, { reason }), 'Payment reversed'); setDecision(null); }}>
        An exact reversing journal is posted today, the invoices reopen and the money receipt is marked cancelled.
      </ConfirmDialog>
      {viewing && <FileViewer doc={viewing} onClose={() => setViewing(null)} />}
    </Screen>
  );
}

