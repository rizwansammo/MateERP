/* eslint-disable @next/next/no-img-element -- documents render private, auth-gated assets */
import type { CSSProperties } from 'react';

import type { BrandingConfig, CompanySnapshot } from '@/lib/api/types';

import type { MoneyFormat } from './money';
import type { SampleInvoice } from './sample';
import { type InvoiceView, sampleInvoiceView } from './view';

/*
 * Official invoice layouts — Meridian, Ledger and Atlas — reproduced from the
 * approved MateERP-UI prototype. Pure and props-driven: branding previews pass
 * the sample invoice, issued documents pass a server-formatted ``view`` built
 * from their frozen snapshot. The server renders the same layouts to PDF.
 * A4 at 96 dpi: 794 × 1123 px. Document colours are fixed print colours.
 */

export interface DocumentBranding {
  config: BrandingConfig;
  company: CompanySnapshot;
  logoUrl: string | null;
  signatureUrl: string | null;
  sealImageUrl: string | null;
}

export const FONT_STACKS = {
  sans: "var(--font-plex-sans), 'IBM Plex Sans', Arial, sans-serif",
  serif: "var(--font-plex-serif), 'IBM Plex Serif', Georgia, serif",
  mono: "var(--font-plex-mono), 'IBM Plex Mono', monospace",
  signature: "var(--font-signature), 'Herr Von Muellerhoff', cursive",
};

export function documentFonts(config: BrandingConfig) {
  const ff = config.typography === 'serif' ? FONT_STACKS.serif : FONT_STACKS.sans;
  const nf = config.typography === 'mono' ? FONT_STACKS.mono : ff;
  return { ff, nf };
}

export function initialsOf(name: string): string {
  return (name || 'MateERP').split(/\s+/).filter(Boolean).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
}

const SPACING = { compact: ['30px', '12px', '5px'], regular: ['42px', '18px', '8px'], airy: ['54px', '24px', '11px'] } as const;
const label: CSSProperties = { fontSize: '9px', letterSpacing: '.12em', textTransform: 'uppercase' };

interface InvoiceDocumentProps {
  branding: DocumentBranding;
  /** Sample content (branding previews). */
  invoice?: SampleInvoice;
  /** Server-formatted content (drafts and issued snapshots). Takes precedence. */
  view?: InvoiceView;
  number: string;
  /** Currency presentation for sample content. */
  format?: MoneyFormat;
  taxLabel?: string;
  watermark?: string;
}

export function InvoiceDocument({ branding, invoice, view, number, format, taxLabel = 'VAT', watermark }: InvoiceDocumentProps) {
  const { config: b, company: co, logoUrl } = branding;
  const { ff, nf } = documentFonts(b);
  const [pad, gap, rowPad] = SPACING[b.spacing];
  const brand = b.brand_color;
  const accent = b.accent_color;
  const tpl = b.invoice_template;
  const ts = b.table_style;
  const hd = b.header_layout;
  const legalName = co.legal_name || co.display_name;
  const address = co.address_lines.join('\n');
  const initials = initialsOf(co.display_name);
  const logoH = `${b.logo_size}px`;
  const cur = invoice?.currency ?? 'BDT';
  const fmt: MoneyFormat = format ?? { currency: cur, symbol: cur, display: 'code', grouping: 'international' };
  const v = view ?? sampleInvoiceView(invoice!, fmt, taxLabel);
  const credit = v.title === 'credit_note';
  const titles = credit
    ? { meridian: 'CREDIT NOTE', ledger: 'Credit Note', atlas: 'Credit note' }
    : { meridian: 'INVOICE', ledger: 'Tax Invoice', atlas: 'Invoice' };

  const headDir = hd === 'logo-right' ? 'row-reverse' : hd === 'centered' ? 'column' : 'row';
  const headAlign = hd === 'centered' ? 'center' : 'flex-start';
  const headText = hd === 'centered' ? 'center' : 'left';
  const titleAlign = hd === 'centered' ? 'center' : hd === 'logo-right' ? 'flex-start' : 'flex-end';

  const heads: [string, 'left' | 'right'][] = [['#', 'left'], ['Description', 'left'], ['Qty', 'right'], ['Unit price', 'right'], ['Disc.', 'right'], ['Tax', 'right'], ['Amount', 'right']];
  const grid = '28px minmax(0,1fr) 54px 92px 50px 54px 100px';
  const thBg = tpl === 'ledger' ? 'transparent' : ts === 'boxed' ? '#F3F4F6' : brand;
  const thFg = tpl === 'ledger' || ts === 'boxed' ? '#111827' : '#FFFFFF';
  const thBd = tpl === 'ledger' ? '1.5px solid #111827' : '0';
  const rowBd = ts === 'striped' ? '0' : '1px solid #E5E7EB';
  const custom = b.custom_fields;
  const showSignature = b.show_signature_on_invoice && (branding.signatureUrl || b.signature_name);

  const logoOrMark = (maxWidth: string) =>
    logoUrl ? (
      <img src={logoUrl} alt="" style={{ height: logoH, maxWidth, objectFit: 'contain' }} />
    ) : null;

  return (
    <div
      data-findoc={credit ? 'credit_note' : 'invoice'}
      data-template={tpl}
      style={{ position: 'relative', width: '794px', minHeight: '1123px', background: '#FFFFFF', color: '#111827', fontFamily: ff, display: 'flex', boxSizing: 'border-box', overflow: 'hidden', fontSize: '11.5px', lineHeight: 1.45 }}
    >
      {tpl === 'atlas' && (
        <div style={{ width: '220px', flex: 'none', background: brand, color: '#FFFFFF', padding: `${pad} 26px`, display: 'flex', flexDirection: 'column', gap: '26px', boxSizing: 'border-box' }}>
          {logoUrl ? (
            <img src={logoUrl} alt="" style={{ height: logoH, maxWidth: '168px', objectFit: 'contain', objectPosition: 'left', background: '#fff', padding: '6px' }} />
          ) : (
            <div style={{ width: '48px', height: '48px', background: accent, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '18px', letterSpacing: '.04em' }}>{initials}</div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div style={{ fontSize: '14px', fontWeight: 600 }}>{legalName}</div>
            <div style={{ whiteSpace: 'pre-line', opacity: 0.82, fontSize: '10.5px' }}>{address}</div>
            {[co.email, co.phone, co.website].filter(Boolean).map((x) => (
              <div key={x} style={{ opacity: 0.82, fontSize: '10.5px' }}>{x}</div>
            ))}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {v.meta.map((m) => (
              <div key={m.label}>
                <div style={{ ...label, opacity: 0.7 }}>{m.label}</div>
                <div style={{ fontSize: '12px', fontWeight: 600, fontFamily: nf }}>{m.value}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '3px' }}>
            {custom.map((c) => <div key={c.label} style={{ fontSize: '9.5px', opacity: 0.8 }}>{c.label}: {c.value}</div>)}
          </div>
        </div>
      )}

      <div style={{ flex: 1, minWidth: 0, padding: pad, display: 'flex', flexDirection: 'column', gap, boxSizing: 'border-box', position: 'relative' }}>
        {tpl === 'meridian' && (
          <>
            <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: '7px', background: brand }} />
            <div style={{ position: 'absolute', left: 0, top: 0, height: '7px', width: '180px', background: accent }} />
            <div style={{ display: 'flex', flexDirection: headDir, alignItems: headAlign, justifyContent: 'space-between', gap: '24px', textAlign: headText, marginTop: '8px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: headAlign }}>
                {logoOrMark('240px') ?? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{ width: '40px', height: '40px', background: brand, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '15px' }}>{initials}</div>
                    <div style={{ fontSize: '17px', fontWeight: 700, color: brand, letterSpacing: '-.01em' }}>{co.display_name}</div>
                  </div>
                )}
                <div style={{ color: '#4B5563', fontSize: '10.5px', lineHeight: 1.5 }}>
                  <div style={{ fontWeight: 600, color: '#111827' }}>{legalName}</div>
                  <div style={{ whiteSpace: 'pre-line' }}>{address}</div>
                  <div>{[co.email, co.phone].filter(Boolean).join(' · ')}</div>
                  <div>{co.website}</div>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: titleAlign, gap: '4px' }}>
                <div style={{ fontSize: '30px', fontWeight: 700, letterSpacing: '.14em', color: brand }}>{titles.meridian}</div>
                <div style={{ fontFamily: nf, fontSize: '13px', fontWeight: 600 }}>{number}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', color: '#4B5563', fontSize: '10px', alignItems: titleAlign }}>
                  {custom.map((c) => <span key={c.label}>{c.label}: {c.value}</span>)}
                </div>
              </div>
            </div>
          </>
        )}

        {tpl === 'ledger' && (
          <div style={{ display: 'flex', flexDirection: headDir, alignItems: headAlign, justifyContent: 'space-between', gap: '24px', paddingBottom: '18px', borderBottom: '2px solid #111827', textAlign: headText }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', alignItems: headAlign }}>
              {logoOrMark('220px')}
              <div style={{ fontSize: '19px', fontWeight: 600, letterSpacing: '-.01em' }}>{legalName}</div>
              <div style={{ color: '#4B5563', fontSize: '10.5px', whiteSpace: 'pre-line' }}>{address}</div>
              <div style={{ color: '#4B5563', fontSize: '10.5px' }}>{[co.email, co.phone, co.website].filter(Boolean).join(' · ')}</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: titleAlign }}>
              <div style={{ fontSize: '11px', letterSpacing: '.3em', textTransform: 'uppercase', color: '#6B7280' }}>{titles.ledger}</div>
              <div style={{ fontFamily: nf, fontSize: '20px', fontWeight: 600, color: accent }}>{number}</div>
              {custom.map((c) => <span key={c.label} style={{ color: '#4B5563', fontSize: '10px' }}>{c.label} {c.value}</span>)}
            </div>
          </div>
        )}

        {tpl === 'atlas' && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: '16px', paddingBottom: '14px', borderBottom: '1px solid #E5E7EB' }}>
            <div style={{ fontSize: '34px', fontWeight: 700, letterSpacing: '.06em', color: brand }}>{titles.atlas}</div>
            <div style={{ fontFamily: nf, fontSize: '14px', fontWeight: 600, color: accent }}>{number}</div>
          </div>
        )}

        {tpl !== 'atlas' && (
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${v.meta.length}, minmax(0,1fr))`, borderTop: '1px solid #E5E7EB', borderBottom: '1px solid #E5E7EB' }}>
            {v.meta.map((m) => (
              <div key={m.label} style={{ padding: '9px 0', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <span style={{ ...label, color: '#6B7280' }}>{m.label}</span>
                <span style={{ fontFamily: nf, fontWeight: 600, fontSize: '11.5px' }}>{m.value}</span>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '28px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
            <div style={{ fontSize: '9px', letterSpacing: '.14em', textTransform: 'uppercase', color: accent, fontWeight: 700, marginBottom: '3px' }}>Bill to</div>
            <div style={{ fontSize: '13px', fontWeight: 600 }}>{v.customer.name}</div>
            {v.customer.contact && <div style={{ color: '#374151' }}>Attn: {v.customer.contact}</div>}
            <div style={{ whiteSpace: 'pre-line', color: '#374151' }}>{v.customer.address}</div>
            {v.customer.country && <div style={{ color: '#374151' }}>{v.customer.country}</div>}
            <div style={{ color: '#6B7280', fontSize: '10.5px' }}>{v.customer.taxId}</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
            {v.reference && (
              <>
                <div style={{ fontSize: '9px', letterSpacing: '.14em', textTransform: 'uppercase', color: accent, fontWeight: 700, marginBottom: '3px' }}>{v.reference.title}</div>
                <div style={{ fontWeight: 600 }}>{v.reference.name}</div>
                {v.reference.code && <div style={{ fontFamily: nf, color: '#6B7280', fontSize: '10.5px' }}>{v.reference.code}</div>}
                {v.reference.description && <div style={{ color: '#374151', marginTop: '4px', textWrap: 'pretty' }}>{v.reference.description}</div>}
              </>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', border: ts === 'boxed' ? '1px solid #D1D5DB' : '0' }}>
          <div style={{ display: 'grid', gridTemplateColumns: grid, background: thBg, color: thFg, borderBottom: thBd }}>
            {heads.map(([t, a]) => (
              <div key={t} style={{ padding: '8px 6px', fontSize: '9px', fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', textAlign: a }}>{t}</div>
            ))}
          </div>
          {v.lines.map((line, i) => {
            const cell: CSSProperties = { padding: `${rowPad} 6px`, textAlign: 'right', fontFamily: nf, fontVariantNumeric: 'tabular-nums' };
            return (
              <div key={`${i}-${line.description}`} style={{ display: 'grid', gridTemplateColumns: grid, background: ts === 'striped' && i % 2 ? 'rgba(17,24,39,.035)' : 'transparent', borderBottom: rowBd }}>
                <div style={{ padding: `${rowPad} 6px`, color: '#9CA3AF', fontFamily: nf }}>{String(i + 1).padStart(2, '0')}</div>
                <div style={{ padding: `${rowPad} 6px`, display: 'flex', flexDirection: 'column', gap: '1px' }}>
                  <span style={{ fontWeight: 500 }}>{line.description}</span>
                  {line.detail && <span style={{ color: '#6B7280', fontSize: '10px' }}>{line.detail}</span>}
                </div>
                <div style={cell}>{line.quantity}</div>
                <div style={cell}>{line.unitPrice}</div>
                <div style={{ ...cell, color: '#6B7280' }}>{line.discount}</div>
                <div style={{ ...cell, color: '#6B7280' }}>{line.tax}</div>
                <div style={{ ...cell, fontWeight: 600 }}>{line.amount}</div>
              </div>
            );
          })}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '28px', alignItems: 'flex-start' }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '12px', minWidth: 0 }}>
            {b.payment_instructions && v.showPaymentInstructions && (
              <div style={{ background: '#F9FAFB', borderTop: `2px solid ${accent}`, padding: '10px 12px' }}>
                <div style={{ fontSize: '9px', letterSpacing: '.14em', textTransform: 'uppercase', fontWeight: 700, color: accent, marginBottom: '4px' }}>Payment instructions</div>
                <div style={{ whiteSpace: 'pre-line', color: '#374151', fontSize: '10.5px' }}>{b.payment_instructions}</div>
              </div>
            )}
            {v.notes && (
              <div>
                <div style={{ fontSize: '9px', letterSpacing: '.14em', textTransform: 'uppercase', fontWeight: 700, color: '#6B7280', marginBottom: '3px' }}>Notes</div>
                <div style={{ whiteSpace: 'pre-line', color: '#374151', fontSize: '10.5px' }}>{v.notes}</div>
              </div>
            )}
          </div>
          <div style={{ width: '270px', flex: 'none', display: 'flex', flexDirection: 'column' }}>
            {v.totals.map((t) => (
              <div key={t.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid #F3F4F6', color: '#374151' }}>
                <span>{t.label}</span>
                <span style={{ fontFamily: nf, fontVariantNumeric: 'tabular-nums' }}>{t.value}</span>
              </div>
            ))}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', marginTop: '6px', background: tpl === 'ledger' ? 'transparent' : brand, color: tpl === 'ledger' ? '#111827' : '#FFFFFF', borderTop: tpl === 'ledger' ? '2px solid #111827' : '0' }}>
              <span style={{ fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', fontSize: '10.5px' }}>{v.totalLabel}</span>
              <span style={{ fontFamily: nf, fontSize: '16px', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{v.total}</span>
            </div>
            {v.dueLine && <div style={{ textAlign: 'right', color: '#6B7280', fontSize: '10px', marginTop: '6px' }}>{v.dueLine}</div>}
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: '24px', marginTop: 'auto', paddingTop: '16px' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {b.terms && v.showTerms && (
              <>
                <div style={{ fontSize: '9px', letterSpacing: '.14em', textTransform: 'uppercase', fontWeight: 700, color: '#6B7280', marginBottom: '3px' }}>Terms &amp; conditions</div>
                <div style={{ color: '#4B5563', fontSize: '10px', whiteSpace: 'pre-line', textWrap: 'pretty' }}>{b.terms}</div>
              </>
            )}
          </div>
          {showSignature && <Signature branding={branding} />}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', borderTop: '1px solid #E5E7EB', paddingTop: '10px', color: '#6B7280', fontSize: '9.5px' }}>
          <span>{b.footer_text}</span>
          <span style={{ fontFamily: nf }}>{number} · Page 1 of 1</span>
        </div>
      </div>

      {watermark && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
          <div style={{ transform: 'rotate(-28deg)', fontSize: '120px', fontWeight: 800, letterSpacing: '.1em', color: 'rgba(17,24,39,.07)', border: '8px solid rgba(17,24,39,.07)', padding: '0 30px' }}>{watermark}</div>
        </div>
      )}
    </div>
  );
}

export function Signature({ branding, compact = false }: { branding: DocumentBranding; compact?: boolean }) {
  const b = branding.config;
  const h = compact ? '42px' : '46px';
  return (
    <div style={{ width: compact ? '190px' : '200px', flex: 'none', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}>
      {branding.signatureUrl ? (
        <img src={branding.signatureUrl} alt="" style={{ height: h, maxWidth: compact ? '170px' : '180px', objectFit: 'contain' }} />
      ) : (
        <div style={{ fontFamily: FONT_STACKS.signature, fontSize: compact ? '34px' : '36px', lineHeight: 1, color: '#1F2A44', height: h, display: 'flex', alignItems: 'flex-end' }}>
          {b.signature_name}
        </div>
      )}
      <div style={{ width: '100%', borderTop: '1px solid #9CA3AF', paddingTop: compact ? '3px' : '4px', textAlign: 'center', fontSize: '10.5px', fontWeight: 600 }}>
        {b.signature_name || 'Authorised signatory'}
      </div>
      <div style={{ fontSize: '9.5px', color: '#6B7280' }}>{[b.signature_title, 'Authorised signatory'].filter(Boolean).join(' · ')}</div>
    </div>
  );
}
