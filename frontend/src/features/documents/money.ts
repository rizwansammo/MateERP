/*
 * Integer minor-unit helpers for document rendering. Amounts are integers
 * (e.g. paisa / cents); no floating-point arithmetic is used for money.
 */

export type Grouping = 'international' | 'south_asian';

function group(whole: string, grouping: Grouping): string {
  if (grouping === 'international' || whole.length <= 3) {
    return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  const last3 = whole.slice(-3);
  const rest = whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',');
  return `${rest},${last3}`;
}

/** Format integer minor units with two decimals: 12345678 → "1,23,456.78". */
export function formatMinor(minor: number, grouping: Grouping = 'international'): string {
  if (!Number.isSafeInteger(minor)) throw new Error('Amounts must be integer minor units.');
  const negative = minor < 0;
  const abs = Math.abs(minor);
  const whole = group(String(Math.floor(abs / 100)), grouping);
  const cents = String(abs % 100).padStart(2, '0');
  return `${negative ? '−' : ''}${whole}.${cents}`;
}

export interface MoneyFormat {
  currency: string;
  symbol: string;
  display: 'symbol' | 'code';
  grouping: Grouping;
}

/** Map the document display settings from the API to a MoneyFormat. */
export function toMoneyFormat(d: {
  currency: string;
  symbol: string;
  currency_display: 'symbol' | 'code';
  number_grouping: Grouping;
}): MoneyFormat {
  return { currency: d.currency, symbol: d.symbol, display: d.currency_display, grouping: d.number_grouping };
}

/** Amount with currency, as configured in Settings → Currency (৳1,25,000.00 or BDT 1,25,000.00). */
export function formatAmount(minor: number, fmt: MoneyFormat): string {
  const value = formatMinor(minor, fmt.grouping);
  return fmt.display === 'symbol' ? `${fmt.symbol}${value}` : `${fmt.currency} ${value}`;
}

/** Round (minor × basisPoints / 10000) half away from zero, in integers. */
export function percentOf(minor: number, basisPoints: number): number {
  const product = minor * basisPoints;
  const quotient = Math.trunc(product / 10000);
  const remainder = Math.abs(product % 10000);
  return remainder * 2 >= 10000 ? quotient + Math.sign(product) : quotient;
}

const ONES = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven',
  'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen'];
const TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];

function belowHundred(n: number): string {
  if (n < 20) return ONES[n] ?? '';
  const tens = TENS[Math.floor(n / 10)] ?? '';
  return n % 10 ? `${tens}-${ONES[n % 10]}` : tens;
}

function belowThousand(n: number): string {
  const hundreds = Math.floor(n / 100);
  const rest = n % 100;
  const parts = [];
  if (hundreds) parts.push(`${ONES[hundreds]} Hundred`);
  if (rest) parts.push(belowHundred(rest));
  return parts.join(' ');
}

const CURRENCY_WORDS: Record<string, [string, string]> = {
  BDT: ['Taka', 'Poisha'],
  USD: ['US Dollars', 'Cents'],
  EUR: ['Euros', 'Cents'],
  GBP: ['Pounds Sterling', 'Pence'],
  SGD: ['Singapore Dollars', 'Cents'],
  INR: ['Rupees', 'Paise'],
};

/** Amount in words, using lakh/crore for South Asian currencies. */
export function amountInWords(minor: number, currency: string): string {
  let n = Math.floor(Math.abs(minor) / 100);
  const fraction = Math.abs(minor) % 100;
  const parts: string[] = [];
  if (currency === 'BDT' || currency === 'INR') {
    const scales: [number, string][] = [[10_000_000, 'Crore'], [100_000, 'Lakh'], [1000, 'Thousand']];
    for (const [size, name] of scales) {
      const count = Math.floor(n / size);
      if (count) parts.push(`${count >= 100 ? belowThousand(count) : belowHundred(count)} ${name}`);
      n %= size;
    }
  } else {
    const scales: [number, string][] = [[1_000_000_000, 'Billion'], [1_000_000, 'Million'], [1000, 'Thousand']];
    for (const [size, name] of scales) {
      const count = Math.floor(n / size);
      if (count) parts.push(`${belowThousand(count)} ${name}`);
      n %= size;
    }
  }
  if (n) parts.push(belowThousand(n));
  const words = parts.join(' ') || 'Zero';
  const [major, minorName] = CURRENCY_WORDS[currency] ?? [currency, 'Cents'];
  const tail = fraction ? ` and ${belowHundred(fraction)} ${minorName}` : '';
  return currency === 'BDT' ? `Taka ${words}${tail} Only` : `${words} ${major}${tail} Only`;
}
