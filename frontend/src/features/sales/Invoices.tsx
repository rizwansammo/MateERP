'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Icon } from '@/components/ui/Icon';
import { api, errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';

import { Screen } from '@/features/commerce/forms';
import { FileViewer } from '@/features/commerce/FileViewer';
import {
  Activity,
  Card,
  DocumentBundle,
  LedgerImpact,
  Lifecycle,
  PdfState,
  act,
  overdueDays,
  positive,
  statusLabel,
  sumDecimals,
  useApi,
  useMoney,
} from '@/features/commerce/shared';
import type { Customer, FiledDocument, Invoice } from '@/features/commerce/types';
import { toEditLines, useCalculation } from '@/features/commerce/lines';
import { UploadDrawer } from '@/features/filing/UploadDrawer';

import { CreditNoteDrawer } from './Credits';
import { RecordPaymentDrawer } from './Payments';
import { InvoicePaper, draftView, issuedView, useDocFormat } from './preview';
import { InvoiceTable } from './tables';

const EYEBROW = 'Sales & Billing';

function NewInvoiceLink() {
  return (
    <Link href="/sales/invoices/new" className="inline-flex h-[34px] items-center gap-1.5 border border-pr bg-pr px-[14px] text-[12.5px] font-semibold text-prt hover:no-underline">
      <Icon name="add" size={17} /> Create invoice
    </Link>
  );
}

export function InvoicesPage({ filter }: { filter?: string }) {
  const { can } = useAuth();
  return (
    <Screen
      eyebrow={EYEBROW}
      title="Invoices"
      description="Every client invoice — drafts, issued, partially paid, paid, overdue and void."
      actions={can('invoices.create') && <NewInvoiceLink />}
    >
      <InvoiceTable filters defaultFilter={filter} />
    </Screen>
  );
}

function scaled(value: string) {
  const [w = '0', f = ''] = value.replace('-', '').split('.');
  return BigInt(w + f.padEnd(6, '0').slice(0, 6));
}

/** Share of the total as a CSS width (exact integer arithmetic, basis points). */
function pct(part: string, total: string) {
  const t = scaled(total);
  if (t === 0n) return '0%';
  const bp = (scaled(part) * 10000n) / t;
  return `${Number(bp > 10000n ? 10000n : bp) / 100}%`;
}

export function InvoiceDetail({ id }: { id: string }) {
  const { can } = useAuth();
  const router = useRouter();
  const money = useMoney();
  const query = useApi<Invoice>(`/billing/invoices/${id}/`);
  const inv = query.data;
  const customer = useApi<Customer>(inv ? `/sales/customers/${inv.customer_id}/` : null);
  const fmt = useDocFormat(inv?.currency ?? 'BDT');
  const draftLines = inv && !inv.number ? toEditLines(inv.lines, 'revenue_account_id') : [];
  const calc = useCalculation({
    currency: inv && !inv.number ? inv.currency : '',
    date: inv?.issue_date ?? '',
    lines: draftLines,
    pricesIncludeTax: inv?.prices_include_tax ?? false,
    discountType: inv?.discount_type,
    discountValue: inv?.discount_value,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<'void' | 'cancel' | null>(null);
  const [drawer, setDrawer] = useState<'pay' | 'credit' | 'proof' | null>(null);
  const [viewing, setViewing] = useState<FiledDocument | null>(null);

  if (!inv) {
    return (
      <Screen eyebrow="Invoice" title={query.error ? 'Invoice not found' : 'Loading…'}>
        {Boolean(query.error) && <Banner tone="err">{errorMessage(query.error)}</Banner>}
      </Screen>
    );
  }

  const isDraft = !inv.number;
  const cur = inv.currency;
  const run = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setError(null);
    try {
      await act(action, message);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const pending = sumDecimals(inv.allocations.filter((a) => a.status === 'pending_verification' || a.status === 'awaiting_approval').map((a) => a.amount));
  const open = inv.status === 'issued' || inv.status === 'partially_paid';
  const actions = [];
  if (isDraft && inv.status !== 'cancelled') {
    if (can('invoices.create')) {
      actions.push(
        <Button key="cancel" variant="danger" icon="delete" disabled={busy || inv.status === 'pending_approval'} onClick={() => setConfirm('cancel')}>
          Cancel draft
        </Button>,
      );
      if (inv.status !== 'pending_approval') {
        actions.push(
          <Link key="edit" href={`/sales/invoices/${inv.id}/edit`} className="inline-flex h-[34px] items-center gap-1.5 border border-bd2 bg-sf px-[14px] text-[12.5px] font-medium text-tx hover:no-underline">
            <Icon name="edit" size={17} /> Edit draft
          </Link>,
        );
      }
    }
    if (can('invoices.issue') && inv.status === 'draft') {
      actions.push(
        <Button key="approve" icon="task_alt" disabled={busy} onClick={() => run(() => api.post(`/billing/invoices/${inv.id}/approve/`), 'Approval recorded')}>
          Approve
        </Button>,
      );
    }
    if (can('invoices.issue') && (inv.status === 'draft' || inv.status === 'approved')) {
      actions.push(
        <Button key="issue" variant="primary" icon="send" disabled={busy} onClick={() => run(() => api.post(`/billing/invoices/${inv.id}/issue/`), 'Invoice issued and filed in Client Documents')}>
          Issue invoice
        </Button>,
      );
    }
  } else if (!isDraft && inv.status !== 'void') {
    if (can('invoices.issue') && !positive(inv.amount_paid) && !positive(inv.amount_credited) && !positive(pending)) {
      actions.push(
        <Button key="void" variant="danger" icon="block" disabled={busy} onClick={() => setConfirm('void')}>
          Void
        </Button>,
      );
    }
    if (can('credit_notes.manage')) {
      actions.push(
        <Button key="credit" icon="remove_circle" onClick={() => setDrawer('credit')}>
          Credit note
        </Button>,
      );
    }
    if (can('payments.record') && open) {
      actions.push(
        <Button key="pay" variant="primary" icon="payments" onClick={() => setDrawer('pay')}>
          Record payment
        </Button>,
      );
    }
  }

  const view = isDraft
    ? draftView(
        {
          issue_date: inv.issue_date,
          due_date: inv.due_date,
          currency: cur,
          reference: inv.reference,
          notes: inv.notes,
          prices_include_tax: inv.prices_include_tax,
          customer: customer.data,
          descriptions: inv.lines.map((l) => l.description),
          discountTypes: inv.lines.map((l) => l.discount_type),
          discountValues: inv.lines.map((l) => l.discount_value),
        },
        calc.result,
        fmt,
        'VAT',
      )
    : issuedView(inv);
  const paid = inv.amount_paid;
  const steps = [
    { label: 'Draft', sub: formatDate(inv.created_at), done: true },
    { label: 'Approved', sub: inv.approved_at ? formatDate(inv.approved_at) : 'Pending', done: Boolean(inv.approved_at) || !isDraft },
    { label: 'Issued', sub: inv.issued_at ? formatDate(inv.issued_at) : 'Pending', done: !isDraft },
    { label: 'Payment received', sub: positive(paid) ? money(paid, cur) : '—', done: positive(paid) },
    {
      label: 'Settled',
      sub: inv.status === 'paid' || inv.status === 'credited' ? 'Settled' : !isDraft ? `${money(inv.outstanding, cur)} open` : '—',
      done: inv.status === 'paid' || inv.status === 'credited',
    },
  ];
  const banner =
    inv.status === 'void' ? (
      <Banner tone="neutral">
        Voided — {inv.void_reason}. The original entry and its exact reversal remain in the ledger.
      </Banner>
    ) : inv.status === 'cancelled' ? (
      <Banner tone="neutral">This draft was cancelled. It never had an accounting effect.</Banner>
    ) : inv.is_overdue ? (
      <Banner tone="err">
        {overdueDays(inv.due_date)} days overdue. {money(inv.outstanding, cur)} remains outstanding
        {positive(paid) ? ` after ${inv.allocations.filter((a) => a.status === 'verified').length} payment(s)` : ''}.
      </Banner>
    ) : inv.status === 'pending_approval' ? (
      <Banner tone="warn">Awaiting approval under the invoice approval policy. It cannot be issued or edited until decided.</Banner>
    ) : isDraft ? (
      <Banner tone="info">
        {inv.status === 'approved' ? 'Approved — ready to issue. ' : 'Draft — no accounting impact yet. '}
        Issuing assigns the next invoice number, freezes the customer, company, tax and branding snapshot, posts receivable, revenue and tax, and files the official PDF in Client Documents.
      </Banner>
    ) : null;

  return (
    <Screen
      eyebrow={`Invoice · ${inv.is_overdue ? 'Overdue' : statusLabel(inv.status)}`}
      title={`${inv.number ?? 'Draft invoice'} — ${inv.customer_name}`}
      description={[inv.project_reference, `Issued ${formatDate(inv.issue_date)}`, `Due ${formatDate(inv.due_date)}`].filter(Boolean).join(' · ')}
      actions={actions.length ? <>{actions}</> : undefined}
      meta={[
        { label: 'Total', value: money(inv.total, cur) },
        ...(isDraft || inv.status === 'void'
          ? []
          : [{ label: 'Outstanding', value: money(inv.outstanding, cur), tone: inv.is_overdue ? ('err' as const) : positive(inv.outstanding) ? ('warn' as const) : ('ok' as const) }]),
        ...(inv.exchange_rate && cur !== inv.snapshot.base_currency && !isDraft ? [{ label: 'Book rate', value: `${inv.exchange_rate.replace(/0+$/, '').replace(/\.$/, '')} ${String(inv.snapshot.base_currency)}` }] : []),
        ...(inv.branding_version ? [{ label: 'Branding', value: `Version ${inv.branding_version}` }] : []),
      ]}
    >
      {error && <Banner tone="err">{error}</Banner>}
      <Lifecycle steps={steps} />
      {banner}
      <div className="grid items-start gap-[18px]" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 480px), 1fr))' }}>
        <Card
          title={isDraft ? 'Draft preview' : 'Issued document'}
          subtitle={isDraft ? 'Uses current branding — frozen on issue' : `Snapshot · branding version ${inv.branding_version} · immutable`}
          actions={
            !isDraft && (
              <PdfState
                status={inv.pdf_status}
                url={inv.pdf_url}
                error={inv.pdf_error}
                canRetry={can('invoices.issue') || can('documents.manage')}
                onRetry={() => api.post(`/billing/invoices/${inv.id}/pdf/`)}
              />
            )
          }
        >
          <div className="flex justify-center overflow-hidden bg-sf3 p-[18px]">
            {view && (
              <InvoicePaper
                view={view}
                number={inv.number ?? 'Assigned on issue'}
                version={inv.branding_version}
                company={isDraft ? undefined : (inv.snapshot.company as never)}
                scale={0.7}
                watermark={isDraft ? 'DRAFT' : inv.status === 'void' ? 'VOID' : undefined}
              />
            )}
          </div>
        </Card>
        <div className="flex min-w-0 flex-col gap-[18px]">
          {!isDraft && (
            <Card title="Collection" actions={<span className="text-[12px] text-tx3">{pct(paid, inv.total).replace(/\.\d+%/, '%')} collected</span>}>
              <div className="flex flex-col gap-3 px-4 py-3.5">
                <div className="flex h-2 bg-sf3">
                  <div className="bg-ok" style={{ width: pct(paid, inv.total) }} />
                  <div className="bg-info" style={{ width: pct(inv.amount_credited, inv.total) }} />
                  <div className="bg-warn" style={{ width: pct(pending, inv.total) }} />
                </div>
                {[
                  ['Invoice total', money(inv.total, cur), 'bg-tx', 'font-medium'],
                  ['Verified payments', money(paid, cur), 'bg-ok', 'font-medium'],
                  ['Credit notes', money(inv.amount_credited, cur), 'bg-info', 'font-medium'],
                  ['Pending verification', money(pending, cur), 'bg-warn', 'font-medium'],
                  ['Outstanding', money(inv.outstanding, cur), inv.is_overdue ? 'bg-err' : 'bg-tx3', 'font-bold'],
                ].map(([label, value, dot, weight]) => (
                  <div key={label} className="flex justify-between text-[12.5px]">
                    <span className="flex items-center gap-[7px] text-tx2">
                      <span className={`size-2 ${dot}`} />
                      {label}
                    </span>
                    <span className={`tabular-nums ${weight}`}>{value}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {!isDraft && (
            <Card
              title="Payments & money receipts"
              actions={
                can('payments.record') &&
                open && (
                  <Button size="sm" variant="primary" icon="add" onClick={() => setDrawer('pay')}>
                    Record payment
                  </Button>
                )
              }
            >
              {inv.allocations.length ? (
                inv.allocations.map((a) => {
                  const ok = a.status === 'verified';
                  const waiting = a.status === 'pending_verification' || a.status === 'awaiting_approval';
                  return (
                    <div key={a.payment_id} className="flex items-center gap-3 border-b border-bd px-4 py-[11px] last:border-b-0">
                      <span className={`flex size-[30px] flex-none items-center justify-center ${ok ? 'bg-oks text-ok' : waiting ? 'bg-warns text-warn' : 'bg-errs text-err'}`}>
                        <Icon name={ok ? 'check' : waiting ? 'hourglass_top' : 'close'} size={17} />
                      </span>
                      <Link href={`/sales/payments/${a.payment_id}`} className="flex min-w-0 flex-1 flex-col text-tx hover:no-underline">
                        <span className="text-[12.5px] font-semibold">
                          {money(a.amount, cur)} <span className="font-normal text-tx3">· {a.number}</span>
                        </span>
                        <span className="text-[11.5px] text-tx3">
                          {formatDate(a.date)} · {statusLabel(a.status)}
                        </span>
                      </Link>
                    </div>
                  );
                })
              ) : (
                <div className="px-4 py-5 text-[12.5px] text-tx3">No payments recorded yet.</div>
              )}
            </Card>
          )}
          <DocumentBundle
            query={`invoice=${inv.id}`}
            empty="The invoice PDF is filed here automatically when issued."
            onOpen={setViewing}
            actions={
              <div className="flex gap-2.5 text-[12px]">
                {!isDraft && can('documents.manage') && can('banking.evidence.view') && (
                  <button type="button" className="bg-transparent font-medium text-lk" onClick={() => setDrawer('proof')}>
                    Upload proof
                  </button>
                )}
                {!isDraft && (
                  <Link href={`/client-documents?year=${inv.issue_date.slice(0, 4)}&customer=${inv.customer_id}&invoice=${inv.id}`} className="font-medium">
                    Open folder →
                  </Link>
                )}
              </div>
            }
          />
          <LedgerImpact
            journals={[inv.journal, inv.void_journal]}
            empty="Drafts do not post to the ledger. Issuing the invoice records receivable, revenue and tax."
          />
          <Activity targetType="billing.invoice" targetId={inv.id} />
        </div>
      </div>
      <ConfirmDialog
        open={confirm === 'void'}
        title={`Void ${inv.number}?`}
        confirmLabel="Void invoice"
        danger
        reason="required"
        onCancel={() => setConfirm(null)}
        onConfirm={async (reason) => {
          await act(() => api.post(`/billing/invoices/${inv.id}/void/`, { reason }), 'Invoice voided');
          setConfirm(null);
        }}
      >
        An exact reversing journal is posted today. The invoice remains on record with status Void and its number is never reused.
      </ConfirmDialog>
      <ConfirmDialog
        open={confirm === 'cancel'}
        title="Cancel this draft invoice?"
        confirmLabel="Cancel draft"
        danger
        reason="optional"
        onCancel={() => setConfirm(null)}
        onConfirm={async (reason) => {
          await act(() => api.post(`/billing/invoices/${inv.id}/cancel/`, { reason }), 'Draft cancelled');
          setConfirm(null);
          router.push('/sales/invoices');
        }}
      >
        Drafts have no accounting impact. The record is kept with status Cancelled.
      </ConfirmDialog>
      {drawer === 'pay' && <RecordPaymentDrawer invoice={inv} onClose={() => setDrawer(null)} />}
      {drawer === 'credit' && <CreditNoteDrawer invoice={inv} onClose={() => setDrawer(null)} />}
      {drawer === 'proof' && (
        <UploadDrawer
          area="client"
          initial={{ kind: 'bank_proof', customer_id: String(inv.customer_id), invoice_id: String(inv.id) }}
          onClose={() => setDrawer(null)}
        />
      )}
      {viewing && <FileViewer doc={viewing} onClose={() => setViewing(null)} />}
    </Screen>
  );
}

