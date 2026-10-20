import { render, screen } from '@testing-library/react';

import { CompanySeal } from '@/features/documents/CompanySeal';
import { type DocumentBranding, InvoiceDocument } from '@/features/documents/InvoiceDocument';
import { amountInWords, formatAmount, formatMinor, percentOf } from '@/features/documents/money';
import { isValidNumberFormat, renderNumber } from '@/features/documents/numbering';
import { ReceiptDocument } from '@/features/documents/ReceiptDocument';
import { computeTotals, sampleInvoice } from '@/features/documents/sample';
import type { BrandingConfig } from '@/lib/api/types';

const CONFIG: BrandingConfig = {
  invoice_template: 'meridian', brand_color: '#0B2A4A', accent_color: '#00B0F0', header_layout: 'logo-left',
  typography: 'sans', spacing: 'regular', table_style: 'lined', logo_size: 52, footer_text: 'Thanks!',
  terms: 'Pay in 30 days.', payment_instructions: 'Bank: Example', custom_fields: [{ label: 'BIN', value: '000-1' }],
  signature_name: 'Rizwan', signature_title: 'Co-founder', show_signature_on_invoice: true, show_signature_on_receipt: true,
  receipt_template: 'official', receipt_confirmation: 'Received with thanks.', receipt_footer: 'System generated.',
  show_logo_on_receipt: true, seal: { mode: 'editor', top: 'NETAMATE', center: 'PAID', bottom: 'DHAKA', color: '#1E4FD8', shape: 'circle' },
};

const branding = (config: Partial<BrandingConfig> = {}): DocumentBranding => ({
  config: { ...CONFIG, ...config },
  company: { display_name: 'NetaMate', legal_name: '', address_lines: ['House 7', 'Dhaka 1213'], email: 'hi@example.test', phone: '+880', website: '', tax_id: 'TIN-1', registration_number: '' },
  logoUrl: null,
  signatureUrl: null,
  sealImageUrl: null,
});

describe('money (integer minor units)', () => {
  it('formats with international and lakh grouping', () => {
    expect(formatMinor(12_345_678)).toBe('123,456.78');
    expect(formatMinor(12_345_678, 'south_asian')).toBe('1,23,456.78');
    expect(formatMinor(-5)).toBe('−0.05');
    expect(() => formatMinor(1.5)).toThrow();
  });

  it('rounds percentages half away from zero without floats', () => {
    expect(percentOf(8_500_000, 500)).toBe(425_000);
    expect(percentOf(105, 1500)).toBe(16); // 15.75 → 16
    expect(percentOf(-105, 1500)).toBe(-16);
  });

  it('writes amounts in words', () => {
    expect(amountInWords(10_000_000, 'BDT')).toBe('Taka One Lakh Only');
    expect(amountInWords(123_456_789, 'BDT')).toBe('Taka Twelve Lakh Thirty-Four Thousand Five Hundred Sixty-Seven and Eighty-Nine Poisha Only');
    expect(amountInWords(150_000, 'USD')).toBe('One Thousand Five Hundred US Dollars Only');
  });

  it('computes sample totals exactly', () => {
    const totals = computeTotals(sampleInvoice('BDT').lines);
    expect(totals.subtotal).toBe(19_000_000);
    expect(totals.discount).toBe(425_000);
    expect(totals.total).toBe(totals.subtotal - totals.discount + totals.taxByRate[0]![1]);
  });
});

describe('number formats', () => {
  it('renders tokens', () => {
    expect(renderNumber('INV-{YYYY}-{####}', new Date(2026, 9, 20), 7)).toBe('INV-2026-0007');
    expect(renderNumber('MR/{YY}{MM}/{###}', new Date(2026, 0, 3), 12)).toBe('MR/2601/012');
  });

  it('validates formats like the server', () => {
    expect(isValidNumberFormat('INV-{YYYY}-{####}')).toBeNull();
    expect(isValidNumberFormat('INV-{YYYY}')).toMatch(/sequence/);
    expect(isValidNumberFormat('{####}')).toMatch(/prefix/);
    expect(isValidNumberFormat('INV <b>{###}')).toMatch(/letters/);
  });
});

describe('InvoiceDocument', () => {
  it.each(['meridian', 'ledger', 'atlas'] as const)('renders the %s template with company and totals', (template) => {
    const { container } = render(
      <InvoiceDocument branding={branding({ invoice_template: template })} invoice={sampleInvoice('BDT', new Date(2026, 9, 20))} number="INV-2026-0001" watermark="PREVIEW" />,
    );
    const doc = container.querySelector('[data-findoc="invoice"]')!;
    expect(doc).toHaveAttribute('data-template', template);
    expect(doc).toHaveTextContent('INV-2026-0001');
    expect(doc).toHaveTextContent('NetaMate');
    expect(doc).toHaveTextContent('Payment instructions');
    expect(doc).toHaveTextContent('BIN');
    expect(doc).toHaveTextContent('PREVIEW');
    expect(doc).toHaveTextContent(`BDT ${formatMinor(computeTotals(sampleInvoice('BDT').lines).total)}`);
  });

  it('shows totals with the configured currency symbol and lakh grouping', () => {
    const format = { currency: 'BDT', symbol: '৳', display: 'symbol' as const, grouping: 'south_asian' as const };
    expect(formatAmount(4_025_000, format)).toBe('৳40,250.00');
    expect(formatAmount(4_025_000, { ...format, display: 'code' })).toBe('BDT 40,250.00');
    const { container } = render(<InvoiceDocument branding={branding()} invoice={sampleInvoice('BDT')} number="X-1" format={format} taxLabel="GST" />);
    const total = computeTotals(sampleInvoice('BDT').lines).total;
    expect(container).toHaveTextContent(`৳${formatMinor(total, 'south_asian')}`);
    expect(container).toHaveTextContent('GST 15%');
  });

  it('hides the signature block when disabled', () => {
    render(<InvoiceDocument branding={branding({ show_signature_on_invoice: false })} invoice={sampleInvoice('BDT')} number="X-1" />);
    expect(screen.queryByText(/Authorised signatory/)).not.toBeInTheDocument();
  });
});

describe('ReceiptDocument', () => {
  it('renders the official template with the stamp seal', () => {
    render(<ReceiptDocument branding={branding()} invoice={sampleInvoice('BDT')} invoiceNumber="INV-1" receiptNumber="MR-1" />);
    expect(screen.getByText('OFFICIAL MONEY RECEIPT')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Company seal: NETAMATE · PAID · DHAKA/ })).toBeInTheDocument();
    expect(screen.getByText('Taka One Lakh Only')).toBeInTheDocument();
  });

  it('renders the compact template without a seal when disabled', () => {
    render(<ReceiptDocument branding={branding({ receipt_template: 'compact', seal: { ...CONFIG.seal, mode: 'none' } })} invoice={sampleInvoice('BDT')} invoiceNumber="INV-1" receiptNumber="MR-1" />);
    expect(screen.getByText('Money Receipt')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /Company seal/ })).not.toBeInTheDocument();
  });
});

describe('CompanySeal', () => {
  it('draws square stamps', () => {
    const { container } = render(<CompanySeal seal={{ ...CONFIG.seal, shape: 'square' }} />);
    expect(container.querySelectorAll('rect').length).toBeGreaterThanOrEqual(2);
  });
});
