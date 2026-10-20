/*
 * Display models for the official documents. Every figure is already formatted:
 * the server computes amounts (exact decimal strings) and these helpers only
 * present them. Sample previews are converted to the same model.
 */

import { decimal, minor } from '@/features/accounting/money';
import { formatDate } from '@/lib/format';

import { type MoneyFormat, formatAmount, formatMinor } from './money';
import { type SampleInvoice, SAMPLE_RECEIPT, computeTotals } from './sample';

const ZERO_DECIMAL = new Set(['JPY', 'KRW', 'VND', 'CLP', 'ISK', 'UGX', 'XAF', 'XOF']);

export interface InvoiceViewLine {
  description: string;
  detail?: string;
  quantity: string;
  unitPrice: string;
  discount: string;
  tax: string;
  amount: string;
}

export interface InvoiceView {
  title: 'invoice' | 'credit_note';
  customer: { name: string; contact: string; address: string; country: string; taxId: string };
  reference: { title: string; name: string; code: string; description: string } | null;
  meta: { label: string; value: string }[];
  lines: InvoiceViewLine[];
  totals: { label: string; value: string }[];
  totalLabel: string;
  total: string;
  dueLine: string;
  notes: string;
  showPaymentInstructions: boolean;
  showTerms: boolean;
}

export interface ReceiptView {
  customerName: string;
  rows: { label: string; value: string; mono?: boolean }[];
  amount: string;
  amountWords: string;
  balanceLines: { label: string; value: string }[];
}

/** Format an exact decimal string with the document's currency settings (no floats). */
export function formatDecimal(value: string | undefined | null, fmt: MoneyFormat, withCurrency = true): string {
  if (value === undefined || value === null || value === '') return '—';
  const places = ZERO_DECIMAL.has(fmt.currency) ? 0 : 2;
  let exact: string;
  try {
    exact = decimal(minor(roundHalfUp(value, places), places), places);
  } catch {
    return value;
  }
  const negative = exact.startsWith('-');
  const [whole = '0', frac] = exact.replace('-', '').split('.');
  const grouped =
    fmt.grouping === 'south_asian' && whole.length > 3
      ? `${whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',')},${whole.slice(-3)}`
      : whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const text = `${negative ? '−' : ''}${grouped}${frac !== undefined ? `.${frac}` : ''}`;
  if (!withCurrency) return text;
  return fmt.display === 'symbol' ? `${fmt.symbol}${text}` : `${fmt.currency} ${text}`;
}

/** Round a decimal string half-up to ``places`` using string arithmetic only. */
export function roundHalfUp(value: string, places: number): string {
  const negative = value.trim().startsWith('-');
  const [whole = '0', frac = ''] = value.trim().replace('-', '').split('.');
  if (frac.length <= places) return value;
  const kept = BigInt(`${whole}${frac.slice(0, places)}`);
  const bumped = Number(frac[places]) >= 5 ? kept + 1n : kept;
  const digits = bumped.toString().padStart(places + 1, '0');
  const out = places ? `${digits.slice(0, -places)}.${digits.slice(-places)}` : digits;
  return `${negative ? '-' : ''}${out}`;
}

export function percentText(value: string | undefined | null): string {
  if (!value) return '0%';
  const trimmed = value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
  return `${trimmed}%`;
}

export function quantityText(value: string): string {
  return value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
}

function isZero(value: string | undefined | null) {
  return !value || /^-?0*(\.0*)?$/.test(value);
}

/** Convert the branding sample (integer minor units) to the display model. */
export function sampleInvoiceView(sample: SampleInvoice, fmt: MoneyFormat, taxLabel: string): InvoiceView {
  const totals = computeTotals(sample.lines);
  const pct = (bp: number) => `${(bp / 100).toFixed(bp % 100 ? 1 : 0)}%`;
  return {
    title: 'invoice',
    customer: sample.customer,
    reference: { title: 'Project', name: sample.project.name, code: sample.project.reference, description: sample.project.description },
    meta: [
      { label: 'Invoice date', value: formatDate(sample.issueDate.toISOString()) },
      { label: 'Due date', value: formatDate(sample.dueDate.toISOString()) },
      { label: 'Currency', value: sample.currency },
    ],
    lines: sample.lines.map((line, i) => ({
      description: line.description,
      detail: line.detail,
      quantity: line.quantity,
      unitPrice: formatMinor(line.unitMinor, fmt.grouping),
      discount: line.discountBp ? pct(line.discountBp) : '—',
      tax: line.taxBp ? pct(line.taxBp) : '0%',
      amount: formatMinor(totals.lines[i]!.net, fmt.grouping),
    })),
    totals: [
      { label: 'Subtotal', value: formatAmount(totals.subtotal, fmt) },
      ...(totals.discount ? [{ label: 'Discount', value: `−${formatAmount(totals.discount, fmt)}` }] : []),
      ...totals.taxByRate.map(([bp, tax]) => ({ label: `${taxLabel} ${pct(bp)}`, value: formatAmount(tax, fmt) })),
    ],
    totalLabel: 'Total due',
    total: formatAmount(totals.total, fmt),
    dueLine: `Due by ${formatDate(sample.dueDate.toISOString())}`,
    notes: sample.notes,
    showPaymentInstructions: true,
    showTerms: true,
  };
}

export function sampleReceiptView(sample: SampleInvoice, invoiceNumber: string, fmt: MoneyFormat, words: (minor: number, currency: string) => string): ReceiptView {
  const total = computeTotals(sample.lines).total;
  const amount = Math.min(SAMPLE_RECEIPT.amountMinor, total);
  const balance = total - amount;
  return {
    customerName: sample.customer.name,
    rows: [
      { label: 'Received from', value: sample.customer.name },
      { label: 'Payment date', value: formatDate(sample.issueDate.toISOString()) },
      { label: 'Against invoice', value: invoiceNumber, mono: true },
      { label: 'Payment method', value: SAMPLE_RECEIPT.method },
      { label: 'Invoice total', value: formatAmount(total, fmt), mono: true },
      { label: 'Received into', value: SAMPLE_RECEIPT.account },
      { label: 'Currency', value: sample.currency },
      { label: 'Reference', value: SAMPLE_RECEIPT.reference, mono: true },
    ],
    amount: formatAmount(amount, fmt),
    amountWords: words(amount, sample.currency),
    balanceLines: [
      {
        label: 'Invoice balance after this receipt:',
        value: `${formatAmount(balance, fmt)}${balance <= 0 ? ' — invoice fully settled' : ''}`,
      },
    ],
  };
}

interface SnapshotLine {
  description: string;
  quantity: string;
  unit_price: string;
  discount_type?: string;
  discount_value?: string;
  line_discount?: string;
  amount: string;
  tax_rate?: string;
}

export interface DocumentSnapshot {
  number?: string;
  issue_date: string;
  due_date?: string;
  currency: string;
  reference?: string;
  notes?: string;
  reason?: string;
  invoice_number?: string;
  invoice_issue_date?: string;
  prices_include_tax?: boolean;
  customer: Record<string, string>;
  project?: { reference: string; name: string } | null;
  milestone?: { name: string } | null;
  lines: SnapshotLine[];
  taxes: { code: string; rate: string; tax: string }[];
  totals: Record<string, string>;
  format: MoneyFormat;
  tax_label?: string;
  tax_registration_label?: string;
}

/** Model for a frozen invoice or credit-note snapshot, or a server-calculated draft. */
export function snapshotInvoiceView(doc: DocumentSnapshot, opts: { creditNote?: boolean } = {}): InvoiceView {
  const fmt = doc.format;
  const label = doc.tax_label || 'VAT';
  const included = doc.prices_include_tax ? 'Includes ' : '';
  const customer = doc.customer;
  const discountText = decimal(minor(doc.totals.line_discount ?? '0') + minor(doc.totals.document_discount ?? '0'));
  const reference = opts.creditNote
    ? { title: 'Credits invoice', name: doc.invoice_number ?? '', code: doc.invoice_issue_date ? `Issued ${formatDate(doc.invoice_issue_date)}` : '', description: '' }
    : doc.project
      ? { title: 'Project', name: doc.project.name, code: doc.project.reference, description: doc.milestone ? `Milestone: ${doc.milestone.name}` : '' }
      : doc.reference
        ? { title: 'Your reference', name: doc.reference, code: '', description: '' }
        : null;
  return {
    title: opts.creditNote ? 'credit_note' : 'invoice',
    customer: {
      name: customer.name ?? '',
      contact: customer.contact_name ?? '',
      address: [customer.address, [customer.city, customer.country].filter(Boolean).join(', ')].filter(Boolean).join('\n'),
      country: '',
      taxId: customer.tax_id ? `${doc.tax_registration_label || 'Tax ID'} ${customer.tax_id}` : '',
    },
    reference,
    meta: opts.creditNote
      ? [
          { label: 'Credit note date', value: formatDate(doc.issue_date) },
          { label: 'Original invoice', value: doc.invoice_number ?? '' },
          { label: 'Currency', value: doc.currency },
        ]
      : [
          { label: 'Invoice date', value: formatDate(doc.issue_date) },
          { label: 'Due date', value: formatDate(doc.due_date ?? doc.issue_date) },
          { label: 'Currency', value: doc.currency },
        ],
    lines: doc.lines.map((line) => ({
      description: line.description,
      quantity: quantityText(line.quantity),
      unitPrice: formatDecimal(line.unit_price, fmt, false),
      discount: isZero(line.line_discount)
        ? '—'
        : line.discount_type === 'fixed'
          ? formatDecimal(line.line_discount, fmt, false)
          : percentText(line.discount_value),
      tax: percentText(line.tax_rate),
      amount: formatDecimal(line.amount, fmt, false),
    })),
    totals: [
      { label: 'Subtotal', value: formatDecimal(doc.totals.subtotal, fmt) },
      ...(isZero(discountText) ? [] : [{ label: 'Discount', value: `−${formatDecimal(discountText, fmt)}` }]),
      ...doc.taxes.map((t) => ({ label: `${included}${label} ${percentText(t.rate)}`, value: formatDecimal(t.tax, fmt) })),
    ],
    totalLabel: opts.creditNote ? 'Total credit' : 'Total due',
    total: formatDecimal(doc.totals.total, fmt),
    dueLine: opts.creditNote || !doc.due_date ? '' : `Due by ${formatDate(doc.due_date)}`,
    notes: opts.creditNote ? `Reason: ${doc.reason ?? ''}` : (doc.notes ?? ''),
    showPaymentInstructions: !opts.creditNote,
    showTerms: !opts.creditNote,
  };
}

export interface ReceiptSnapshot {
  customer: { name: string };
  payment_date: string;
  method: string;
  reference?: string;
  bank_account: string;
  amount: string;
  unapplied: string;
  format: MoneyFormat;
  allocations: { number: string; invoice_total: string; balance_after: string }[];
}

export function snapshotReceiptView(doc: ReceiptSnapshot, words: (value: string, currency: string) => string): ReceiptView {
  const fmt = doc.format;
  const sum = (key: 'invoice_total' | 'balance_after') =>
    decimal(doc.allocations.reduce((acc, a) => acc + minor(a[key]), 0n));
  const single = doc.allocations.length === 1 ? doc.allocations[0] : undefined;
  const balanceLines: ReceiptView['balanceLines'] = [];
  if (single) {
    balanceLines.push({
      label: 'Invoice balance after this receipt:',
      value: `${formatDecimal(single.balance_after, fmt)}${isZero(single.balance_after) ? ' — invoice fully settled' : ''}`,
    });
  } else if (doc.allocations.length) {
    balanceLines.push({ label: 'Balance remaining on these invoices:', value: formatDecimal(sum('balance_after'), fmt) });
  }
  if (!isZero(doc.unapplied)) balanceLines.push({ label: 'Held as customer credit:', value: formatDecimal(doc.unapplied, fmt) });
  return {
    customerName: doc.customer.name,
    rows: [
      { label: 'Received from', value: doc.customer.name },
      { label: 'Payment date', value: formatDate(doc.payment_date) },
      {
        label: single || !doc.allocations.length ? 'Against invoice' : 'Against invoices',
        value: doc.allocations.map((a) => a.number).join(', ') || 'Customer credit',
        mono: true,
      },
      { label: 'Payment method', value: doc.method },
      { label: single || !doc.allocations.length ? 'Invoice total' : 'Invoices total', value: formatDecimal(sum('invoice_total'), fmt), mono: true },
      { label: 'Received into', value: doc.bank_account },
      { label: 'Currency', value: fmt.currency },
      { label: 'Reference', value: doc.reference || '—', mono: true },
    ],
    amount: formatDecimal(doc.amount, fmt),
    amountWords: words(doc.amount, fmt.currency),
    balanceLines,
  };
}
