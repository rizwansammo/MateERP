/* eslint-disable @next/next/no-img-element -- documents render private, auth-gated assets */
import type { CSSProperties } from 'react';

import { CompanySeal } from './CompanySeal';
import { type DocumentBranding, Signature, documentFonts, initialsOf } from './InvoiceDocument';
import { type MoneyFormat, amountInWords } from './money';
import type { SampleInvoice } from './sample';
import { type ReceiptView, sampleReceiptView } from './view';

/*
 * Official money receipt — Official (framed) and Compact layouts from the
 * approved prototype. 794 × 600 px.
 */

interface ReceiptDocumentProps {
  branding: DocumentBranding;
  /** Sample content (branding previews). */
  invoice?: SampleInvoice;
  /** Server-formatted content (issued receipts). Takes precedence. */
  view?: ReceiptView;
  invoiceNumber: string;
  receiptNumber: string;
  format?: MoneyFormat;
  watermark?: string;
}

export function ReceiptDocument({ branding, invoice, view, invoiceNumber, receiptNumber, format, watermark }: ReceiptDocumentProps) {
  const { config: b, company: co, logoUrl } = branding;
  const { ff, nf } = documentFonts(b);
  const brand = b.brand_color;
  const accent = b.accent_color;
  const official = b.receipt_template === 'official';
  const legalName = co.legal_name || co.display_name;
  const showLogo = b.show_logo_on_receipt && Boolean(logoUrl);
  const coLine = [co.address_lines.join(', '), co.phone, co.tax_id].filter(Boolean).join(' · ');
  const cur = invoice?.currency ?? 'BDT';
  const fmt: MoneyFormat = format ?? { currency: cur, symbol: cur, display: 'code', grouping: 'international' };
  const v = view ?? sampleReceiptView(invoice!, invoiceNumber, fmt, amountInWords);
  const rows = v.rows.map((r) => ({ l: r.label, v: r.value, mono: r.mono }));
  const seal = b.seal;
  const sealNode =
    seal.mode === 'image' && branding.sealImageUrl ? (
      <img src={branding.sealImageUrl} alt="Company seal" style={{ width: '112px', height: '112px', objectFit: 'contain', transform: 'rotate(-9deg)', opacity: 0.86, marginBottom: '-6px' }} />
    ) : seal.mode === 'editor' ? (
      <div style={{ transform: 'rotate(-9deg)', opacity: 0.86, marginBottom: '-6px' }}>
        <CompanySeal seal={seal} size={112} />
      </div>
    ) : null;
  const tiny: CSSProperties = { fontSize: '9px', letterSpacing: '.14em', textTransform: 'uppercase' };

  return (
    <div
      data-findoc="receipt"
      data-template={b.receipt_template}
      style={{ position: 'relative', width: '794px', height: '600px', background: '#FFFFFF', color: '#111827', fontFamily: ff, boxSizing: 'border-box', padding: '22px', fontSize: '11.5px', lineHeight: 1.45, overflow: 'hidden' }}
    >
      <div style={{ position: 'relative', height: '100%', boxSizing: 'border-box', border: official ? `2px solid ${brand}` : '1px solid #E5E7EB', outline: official ? `1px solid ${accent}` : '0px solid transparent', outlineOffset: '-7px', padding: '22px 28px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {official ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
                {showLogo ? (
                  <img src={logoUrl!} alt="" style={{ height: '44px', maxWidth: '150px', objectFit: 'contain' }} />
                ) : (
                  <div style={{ width: '42px', height: '42px', background: brand, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '15px' }}>{initialsOf(co.display_name)}</div>
                )}
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: '15px', fontWeight: 700 }}>{legalName}</div>
                  <div style={{ color: '#6B7280', fontSize: '10px' }}>{coLine}</div>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ ...tiny, color: '#6B7280' }}>Receipt No.</div>
                <div style={{ fontFamily: nf, fontSize: '15px', fontWeight: 700, color: brand }}>{receiptNumber}</div>
              </div>
            </div>
            <div style={{ textAlign: 'center', padding: '6px 0', borderTop: '1px solid #E5E7EB', borderBottom: '1px solid #E5E7EB' }}>
              <span style={{ fontSize: '17px', fontWeight: 700, letterSpacing: '.32em', color: brand }}>OFFICIAL MONEY RECEIPT</span>
            </div>
          </>
        ) : (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px', paddingBottom: '12px', borderBottom: `3px solid ${brand}` }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {showLogo && <img src={logoUrl!} alt="" style={{ height: '38px', maxWidth: '150px', objectFit: 'contain', objectPosition: 'left' }} />}
              <div style={{ fontSize: '14px', fontWeight: 700 }}>{legalName}</div>
              <div style={{ color: '#6B7280', fontSize: '10px' }}>{coLine}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '22px', fontWeight: 700, color: brand }}>Money Receipt</div>
              <div style={{ fontFamily: nf, fontSize: '13px', fontWeight: 600 }}>{receiptNumber}</div>
            </div>
          </div>
        )}

        <div style={{ color: '#374151', textWrap: 'pretty' }}>{b.receipt_confirmation}</div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 28px' }}>
          {rows.map((x) => (
            <div key={x.l} style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', padding: '6px 0', borderBottom: '1px dotted #D1D5DB' }}>
              <span style={{ color: '#6B7280' }}>{x.l}</span>
              <span style={{ fontWeight: 600, textAlign: 'right', fontFamily: x.mono ? nf : ff }}>{x.v}</span>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'stretch', gap: '16px' }}>
          <div style={{ flex: 'none', background: brand, color: '#fff', padding: '10px 16px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ ...tiny, opacity: 0.8 }}>Amount received</span>
            <span style={{ fontFamily: nf, fontSize: '22px', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{v.amount}</span>
          </div>
          <div style={{ flex: 1, border: '1px solid #E5E7EB', padding: '8px 12px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ ...tiny, color: '#6B7280' }}>In words</span>
            <span style={{ fontWeight: 600, fontStyle: 'italic', textWrap: 'pretty' }}>{v.amountWords}</span>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: '20px', marginTop: 'auto' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', color: '#6B7280', fontSize: '10px', maxWidth: '330px' }}>
            {v.balanceLines.map((line) => (
              <span key={line.label}>
                {line.label}{' '}
                <b style={{ color: '#111827', fontFamily: nf }}>{line.value}</b>
              </span>
            ))}
            <span>{b.receipt_footer}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '6px' }}>
            {sealNode}
            {b.show_signature_on_receipt && <Signature branding={branding} compact />}
          </div>
        </div>
      </div>

      {watermark && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
          <div style={{ transform: 'rotate(-20deg)', fontSize: '84px', fontWeight: 800, letterSpacing: '.1em', color: 'rgba(17,24,39,.06)' }}>{watermark}</div>
        </div>
      )}
    </div>
  );
}
