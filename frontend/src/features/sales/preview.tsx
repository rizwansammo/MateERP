'use client';

import { useCurrencies } from '@/lib/api/hooks';
import type { BrandingConfig, CompanySnapshot } from '@/lib/api/types';

import { useConfig } from '@/features/accounting/shared';
import { useApi } from '@/features/commerce/shared';
import type { Calculation, Customer, Invoice, InvoiceSnapshot, Receipt } from '@/features/commerce/types';
import { ScaledPage } from '@/features/documents/DocumentStage';
import { InvoiceDocument } from '@/features/documents/InvoiceDocument';
import type { MoneyFormat } from '@/features/documents/money';
import { ReceiptDocument } from '@/features/documents/ReceiptDocument';
import { amountInWordsDecimal } from '@/features/documents/money';
import { type InvoiceView, snapshotInvoiceView, snapshotReceiptView } from '@/features/documents/view';

interface DocumentBranding {
  version: number | null;
  label?: string;
  config: BrandingConfig;
  company: CompanySnapshot;
  logo_url: string | null;
  signature_url: string | null;
  seal_image_url: string | null;
}

export function useDocumentBranding(version?: number | null) {
  return useApi<DocumentBranding>(`/billing/document-branding/${version ? `?version=${version}` : ''}`);
}

export function useDocFormat(currency: string): MoneyFormat {
  const config = useConfig();
  const currencies = useCurrencies();
  return {
    currency,
    symbol: currencies.data?.find((c) => c.code === currency)?.symbol ?? currency,
    display: config.data?.currency_display === 'symbol' ? 'symbol' : 'code',
    grouping: config.data?.number_grouping === 'south_asian' ? 'south_asian' : 'international',
  };
}

function brandingProps(b: DocumentBranding, company?: CompanySnapshot) {
  return {
    config: b.config,
    company: company ?? b.company,
    logoUrl: b.logo_url,
    signatureUrl: b.signature_url,
    sealImageUrl: b.seal_image_url,
  };
}

export interface DraftInput {
  issue_date: string;
  due_date: string;
  currency: string;
  reference: string;
  notes: string;
  prices_include_tax: boolean;
  customer?: Customer;
  project?: { reference: string; name: string } | null;
  milestone?: { name: string } | null;
  descriptions: string[];
  discountTypes: ('percent' | 'fixed')[];
  discountValues: string[];
}

export function draftView(input: DraftInput, calc: Calculation | null, fmt: MoneyFormat, taxLabel: string): InvoiceView {
  const c = input.customer;
  return snapshotInvoiceView({
    issue_date: input.issue_date,
    due_date: input.due_date,
    currency: input.currency,
    reference: input.reference,
    notes: input.notes,
    prices_include_tax: input.prices_include_tax,
    customer: {
      name: c?.name ?? 'Select a customer',
      contact_name: c?.contact_name ?? '',
      address: c?.address ?? '',
      city: c?.city ?? '',
      country: c?.country ?? '',
      tax_id: c?.tax_id ?? '',
    },
    project: input.project ?? null,
    milestone: input.milestone ?? null,
    lines: (calc?.lines ?? []).map((l, i) => ({
      description: input.descriptions[i] ?? '',
      quantity: String(l.quantity ?? '1'),
      unit_price: String(l.unit_price ?? '0'),
      discount_type: input.discountTypes[i] ?? 'percent',
      discount_value: input.discountValues[i] ?? '0',
      line_discount: String(l.line_discount ?? '0'),
      amount: String(l.amount ?? '0'),
      tax_rate: String(l.tax_rate ?? '0'),
    })),
    taxes: (calc?.taxes ?? []).map((t) => ({ code: t.code, rate: t.rate, tax: t.tax })),
    totals: {
      subtotal: calc?.subtotal ?? '0',
      line_discount: calc?.line_discount ?? '0',
      document_discount: calc?.document_discount ?? '0',
      total: calc?.total ?? '0',
    },
    format: fmt,
    tax_label: taxLabel,
  });
}

/** Scaled document card used by the editor and the invoice page. */
export function InvoicePaper({
  view,
  number,
  version,
  company,
  scale,
  watermark,
}: {
  view: InvoiceView;
  number: string;
  version?: number | null;
  company?: CompanySnapshot;
  scale: number;
  watermark?: string;
}) {
  const branding = useDocumentBranding(version);
  if (!branding.data) return <div className="p-6 text-[12.5px] text-tx3">{branding.error ? 'Branding unavailable.' : 'Loading…'}</div>;
  if (!branding.data.version) {
    return <div className="p-6 text-[12.5px] text-tx3">Publish invoice branding in Settings → Branding to preview and issue invoices.</div>;
  }
  return (
    <ScaledPage width={794} height={1123} scale={scale} label="Invoice document">
      <InvoiceDocument branding={brandingProps(branding.data, company)} view={view} number={number} watermark={watermark} />
    </ScaledPage>
  );
}

export function issuedView(invoice: Invoice): InvoiceView | null {
  if (!invoice.number || !hasInvoiceSnapshot(invoice.snapshot)) return null;
  return snapshotInvoiceView(invoice.snapshot);
}

function hasInvoiceSnapshot(value: Invoice['snapshot']): value is InvoiceSnapshot {
  return Array.isArray(value.lines) && typeof value.issue_date === 'string';
}

export function ReceiptPaper({ snapshot, number, version, scale }: { snapshot: Receipt['snapshot']; number: string; version: number; scale: number }) {
  const branding = useDocumentBranding(version);
  if (!branding.data?.version) return <div className="p-6 text-[12.5px] text-tx3">Loading…</div>;
  const words = amountInWordsDecimal;
  const view = snapshotReceiptView(snapshot, words);
  const company = snapshot.company;
  return (
    <ScaledPage width={794} height={600} scale={scale} label="Money receipt">
      <ReceiptDocument branding={brandingProps(branding.data, company)} view={view} invoiceNumber="" receiptNumber={number} />
    </ScaledPage>
  );
}
