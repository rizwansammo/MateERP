/*
 * Clearly fictional sample content for branding previews. Nothing here is a
 * real customer, invoice or payment, and previews are watermarked PREVIEW.
 */

import { percentOf } from './money';

export interface DocLine {
  description: string;
  detail?: string;
  quantity: string;
  unitMinor: number;
  discountBp: number;
  taxBp: number;
}

export interface SampleInvoice {
  customer: { name: string; contact: string; address: string; country: string; taxId: string };
  project: { name: string; reference: string; description: string };
  issueDate: Date;
  dueDate: Date;
  currency: string;
  lines: DocLine[];
  notes: string;
}

export function sampleInvoice(currency: string, today = new Date()): SampleInvoice {
  const due = new Date(today);
  due.setDate(due.getDate() + 30);
  return {
    customer: {
      name: 'Sample Client Ltd.',
      contact: 'Accounts Payable',
      address: 'Level 4, 12 Example Avenue\nSample City 1000',
      country: 'Sampleland',
      taxId: 'Tax ID 000-000-000 (sample)',
    },
    project: {
      name: 'Website redesign (sample project)',
      reference: 'PRJ-SAMPLE-01',
      description: 'Illustrative work used only to preview document branding.',
    },
    issueDate: today,
    dueDate: due,
    currency,
    lines: [
      { description: 'Discovery & planning workshop', quantity: '1', unitMinor: 4_500_000, discountBp: 0, taxBp: 1500 },
      { description: 'Design system & page templates', quantity: '1', unitMinor: 8_500_000, discountBp: 500, taxBp: 1500 },
      { description: 'Front-end development', detail: 'per hour', quantity: '40', unitMinor: 150_000, discountBp: 0, taxBp: 1500 },
    ],
    notes: 'Sample note: this preview does not create an invoice.',
  };
}

export interface Totals {
  lines: { net: number }[];
  subtotal: number;
  discount: number;
  taxByRate: [number, number][];
  total: number;
}

export function computeTotals(lines: DocLine[]): Totals {
  let subtotal = 0;
  let discount = 0;
  const tax = new Map<number, number>();
  const out = lines.map((line) => {
    const gross = line.unitMinor * Number(line.quantity);
    const disc = percentOf(gross, line.discountBp);
    const net = gross - disc;
    subtotal += gross;
    discount += disc;
    if (line.taxBp) tax.set(line.taxBp, (tax.get(line.taxBp) ?? 0) + percentOf(net, line.taxBp));
    return { net };
  });
  const taxTotal = [...tax.values()].reduce((a, b) => a + b, 0);
  return { lines: out, subtotal, discount, taxByRate: [...tax.entries()], total: subtotal - discount + taxTotal };
}

export const SAMPLE_RECEIPT = {
  method: 'Bank Transfer',
  reference: 'SAMPLE-REF-0001',
  account: 'Sample Bank — Operating account',
  amountMinor: 10_000_000,
};
