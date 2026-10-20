'use client';

import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';

import { DarkSegmented, ScaledPage, ViewerToolbar, ZoomControl } from '@/features/documents/DocumentStage';
import { InvoiceDocument } from '@/features/documents/InvoiceDocument';
import { renderNumber } from '@/features/documents/numbering';
import { ReceiptDocument } from '@/features/documents/ReceiptDocument';
import { sampleInvoice } from '@/features/documents/sample';
import { toMoneyFormat } from '@/features/documents/money';
import type { BrandingVersionDetail, DocumentDisplay } from '@/lib/api/types';
import { formatDateTime, titleCase } from '@/lib/format';

/** Read-only preview of a published (immutable) branding version. */
export function VersionViewer({ version, initialDoc = 'invoice', display, onClose }: {
  version: BrandingVersionDetail;
  initialDoc?: 'invoice' | 'receipt';
  display: DocumentDisplay;
  onClose: () => void;
}) {
  const baseCurrency = display.currency;
  const format = toMoneyFormat(display);
  const [doc, setDoc] = useState(initialDoc);
  const [zoom, setZoom] = useState(0.75);
  const sample = useMemo(() => sampleInvoice(baseCurrency), [baseCurrency]);
  const today = new Date();
  const branding = {
    config: version.config,
    company: version.company,
    logoUrl: version.logo_url,
    signatureUrl: version.signature_url,
    sealImageUrl: version.seal_image_url,
  };
  const invoiceNo = renderNumber(version.numbering.invoice, today, 1);
  const receiptNo = renderNumber(version.numbering.receipt, today, 1);

  return createPortal(
    <div role="dialog" aria-modal="true" aria-label="Branding version preview" className="fixed inset-0 z-[70] flex flex-col bg-[#0A0E13] text-[#E6EDF5]">
      <ViewerToolbar
        title={`Version ${version.number}${version.label ? ` · ${version.label}` : ''} — ${titleCase(version.config.invoice_template)}`}
        subtitle={`Published by ${version.published_by} · ${formatDateTime(version.published_at)} · sample data, nothing issued`}
        onClose={onClose}
      >
        <DarkSegmented label="Document" value={doc} onChange={setDoc} options={[{ value: 'invoice', label: 'Invoice' }, { value: 'receipt', label: 'Receipt' }]} />
        <ZoomControl zoom={zoom} onZoom={setZoom} />
      </ViewerToolbar>
      <div className="flex flex-1 justify-center overflow-auto p-8 max-sm:p-4">
        {doc === 'invoice' ? (
          <ScaledPage width={794} height={1123} scale={zoom} label="Invoice preview">
            <InvoiceDocument branding={branding} invoice={sample} number={invoiceNo} format={format} taxLabel={display.tax_label} watermark="PREVIEW" />
          </ScaledPage>
        ) : (
          <ScaledPage width={794} height={600} scale={zoom} label="Money receipt preview">
            <ReceiptDocument branding={branding} invoice={sample} invoiceNumber={invoiceNo} receiptNumber={receiptNo} format={format} watermark="PREVIEW" />
          </ScaledPage>
        )}
      </div>
    </div>,
    document.body,
  );
}
