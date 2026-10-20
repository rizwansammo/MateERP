'use client';

import { useEffect, useState } from 'react';

import { Icon } from '@/components/ui/Icon';
import { AmountInput, Input, Select } from '@/components/ui/Input';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useDebounced } from '@/lib/useDebounced';

import type { Account, Tax } from '@/features/accounting/types';
import { useAccounts } from '@/features/accounting/shared';

import { useApi, useMoney } from './shared';
import type { BillingItem, Calculation, DocLine } from './types';

export interface EditLine {
  item_id: string;
  description: string;
  quantity: string;
  unit_price: string;
  discount_type: 'percent' | 'fixed';
  discount_value: string;
  tax_code_id: string;
  account_id: string;
  sales_order_line_id?: number | null;
}

export function blankLine(taxCodeId = ''): EditLine {
  return {
    item_id: '',
    description: '',
    quantity: '1',
    unit_price: '',
    discount_type: 'percent',
    discount_value: '0',
    tax_code_id: taxCodeId,
    account_id: '',
  };
}

function trim(value: string | null | undefined) {
  if (!value) return '';
  return value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
}

/** Saved document lines → editable strings. */
export function toEditLines(lines: DocLine[], accountKey: 'revenue_account_id' | 'account_id'): EditLine[] {
  return lines.map((l) => ({
    item_id: l.item_id ? String(l.item_id) : '',
    description: l.description,
    quantity: trim(l.quantity),
    unit_price: trim(l.unit_price),
    discount_type: l.discount_type,
    discount_value: trim(l.discount_value) || '0',
    tax_code_id: l.tax_code_id ? String(l.tax_code_id) : '',
    account_id: l[accountKey] ? String(l[accountKey]) : '',
    sales_order_line_id: l.sales_order_line_id ?? null,
  }));
}

/** Editable strings → API payload (decimal strings, ids as numbers). */
export function toPayload(lines: EditLine[], accountKey: 'revenue_account_id' | 'account_id'): (Pick<DocLine, 'description' | 'quantity' | 'unit_price' | 'discount_type' | 'discount_value' | 'tax_code_id' | 'item_id' | 'sales_order_line_id' | 'account_id' | 'revenue_account_id'>)[] {
  return lines
    .filter((l) => l.description.trim() || l.unit_price)
    .map((l) => ({
      ...(l.item_id ? { item_id: Number(l.item_id) } : {}),
      ...(l.sales_order_line_id ? { sales_order_line_id: l.sales_order_line_id } : {}),
      description: l.description.trim(),
      quantity: l.quantity || '1',
      unit_price: l.unit_price || '0',
      discount_type: l.discount_type,
      discount_value: l.discount_value || '0',
      tax_code_id: l.tax_code_id ? Number(l.tax_code_id) : null,
      [accountKey]: l.account_id ? Number(l.account_id) : null,
    }));
}

export function useTaxCodes() {
  return useApi<Page<Tax>>('/accounting/tax-codes/?page_size=100');
}

export function useItems() {
  return useApi<Page<BillingItem>>('/sales/items/?status=active&page_size=100');
}

export function postingAccounts(accounts: Account[] | undefined, kind: 'revenue' | 'expense') {
  const types = kind === 'revenue' ? ['revenue'] : ['expense', 'asset'];
  return (accounts ?? []).filter((a) => types.includes(a.account_type) && a.is_postable && a.is_active && !a.control);
}

/** Debounced server calculation: the browser never computes authoritative totals. */
export function useCalculation(input: {
  currency: string;
  date: string;
  lines: EditLine[];
  pricesIncludeTax: boolean;
  discountType?: 'percent' | 'fixed';
  discountValue?: string;
}) {
  const body = JSON.stringify({
    currency: input.currency,
    date: input.date,
    prices_include_tax: input.pricesIncludeTax,
    discount_type: input.discountType ?? 'percent',
    discount_value: input.discountValue || '0',
    lines: toPayload(input.lines, 'account_id').map((l) => ({
      quantity: l.quantity,
      unit_price: l.unit_price,
      discount_type: l.discount_type,
      discount_value: l.discount_value,
      tax_code_id: l.tax_code_id,
    })),
  });
  const debounced = useDebounced(body, 300);
  const [state, setState] = useState<{ input: string; result: Calculation | null; error: string | null }>({ input: '', result: null, error: null });
  useEffect(() => {
    const payload = JSON.parse(debounced) as { currency: string; date: string; lines: unknown[] };
    if (!payload.currency || !payload.date || !payload.lines.length) {
      return;
    }
    let live = true;
    api
      .post<Calculation>('/sales/calculate/', payload as Record<string, unknown>)
      .then((result) => live && setState({ input: debounced, result, error: null }))
      .catch((e: unknown) => live && setState({ input: debounced, result: null, error: errorMessage(e) }));
    return () => {
      live = false;
    };
  }, [debounced]);
  return state.input === body ? state : { result: null, error: null };
}

const cell = 'border-b border-bd px-2 py-1.5';

export function LinesEditor({
  lines,
  onChange,
  currency,
  calc,
  accountKind,
  withItems = true,
}: {
  lines: EditLine[];
  onChange: (lines: EditLine[]) => void;
  currency: string;
  calc: Calculation | null;
  accountKind: 'revenue' | 'expense';
  withItems?: boolean;
}) {
  const money = useMoney();
  const taxes = useTaxCodes();
  const items = useItems();
  const accounts = useAccounts();
  const options = postingAccounts(accounts.data, accountKind);
  const set = (i: number, patch: Partial<EditLine>) => onChange(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const activeTaxes = (taxes.data?.results ?? []).filter((t) => t.is_active);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] border-collapse text-[12.5px]">
        <thead className="bg-sf2">
          <tr className="border-b border-bd text-[10.5px] font-semibold uppercase tracking-[.07em] text-tx3">
            {withItems && <th className="w-[15%] px-2 py-2 text-left">Catalog</th>}
            <th className="px-2 py-2 text-left">Description</th>
            <th className="w-[70px] px-2 py-2 text-right">Qty</th>
            <th className="w-[110px] px-2 py-2 text-right">Unit price</th>
            <th className="w-[96px] px-2 py-2 text-right">Discount</th>
            <th className="w-[110px] px-2 py-2 text-left">Tax</th>
            <th className="w-[150px] px-2 py-2 text-left">{accountKind === 'revenue' ? 'Revenue account' : 'Account'}</th>
            <th className="w-[110px] px-2 py-2 text-right">Amount</th>
            <th className="w-[34px]" />
          </tr>
        </thead>
        <tbody>
          {lines.map((line, i) => {
            const computed = calc?.lines[i];
            return (
              <tr key={i}>
                {withItems && (
                  <td className={cell}>
                    <Select
                      controlSize="sm"
                      aria-label={`Line ${i + 1} catalog item`}
                      value={line.item_id}
                      onChange={(e) => {
                        const item = items.data?.results.find((x) => String(x.id) === e.target.value);
                        set(
                          i,
                          item
                            ? {
                                item_id: String(item.id),
                                description: item.name,
                                unit_price: trim(item.unit_price),
                                tax_code_id: item.tax_code_id ? String(item.tax_code_id) : line.tax_code_id,
                                account_id: item.revenue_account_id ? String(item.revenue_account_id) : line.account_id,
                              }
                            : { item_id: '' },
                        );
                      }}
                    >
                      <option value="">Custom line</option>
                      {items.data?.results.map((x) => (
                        <option key={x.id} value={x.id}>
                          {x.name}
                        </option>
                      ))}
                    </Select>
                  </td>
                )}
                <td className={cell}>
                  <Input controlSize="sm" aria-label={`Line ${i + 1} description`} value={line.description} onChange={(e) => set(i, { description: e.target.value })} />
                </td>
                <td className={cell}>
                  <AmountInput controlSize="sm" aria-label={`Line ${i + 1} quantity`} value={line.quantity} onChange={(e) => set(i, { quantity: e.target.value })} />
                </td>
                <td className={cell}>
                  <AmountInput controlSize="sm" aria-label={`Line ${i + 1} unit price`} value={line.unit_price} onChange={(e) => set(i, { unit_price: e.target.value })} />
                </td>
                <td className={cell}>
                  <div className="flex">
                    <AmountInput controlSize="sm" aria-label={`Line ${i + 1} discount`} value={line.discount_value} onChange={(e) => set(i, { discount_value: e.target.value })} />
                    <button
                      type="button"
                      aria-label={`Line ${i + 1} discount type`}
                      onClick={() => set(i, { discount_type: line.discount_type === 'percent' ? 'fixed' : 'percent' })}
                      className="h-[30px] w-8 flex-none border border-l-0 border-bd bg-sf2 text-[11.5px] font-medium text-tx2 hover:bg-sf3"
                    >
                      {line.discount_type === 'percent' ? '%' : currency.slice(0, 1) || '#'}
                    </button>
                  </div>
                </td>
                <td className={cell}>
                  <Select controlSize="sm" aria-label={`Line ${i + 1} tax`} value={line.tax_code_id} onChange={(e) => set(i, { tax_code_id: e.target.value })}>
                    <option value="">No tax</option>
                    {activeTaxes.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.code}
                      </option>
                    ))}
                  </Select>
                </td>
                <td className={cell}>
                  <Select controlSize="sm" aria-label={`Line ${i + 1} account`} value={line.account_id} onChange={(e) => set(i, { account_id: e.target.value })}>
                    <option value="">Default</option>
                    {options.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.code} · {a.name}
                      </option>
                    ))}
                  </Select>
                </td>
                <td className={`${cell} text-right font-medium tabular-nums`}>
                  {computed ? money(String(computed.amount), currency) : '—'}
                </td>
                <td className={`${cell} text-center`}>
                  <button
                    type="button"
                    aria-label={`Remove line ${i + 1}`}
                    disabled={lines.length === 1}
                    onClick={() => onChange(lines.filter((_, j) => j !== i))}
                    className="flex size-7 items-center justify-center bg-transparent text-tx3 hover:text-err disabled:opacity-30"
                  >
                    <Icon name="close" size={16} />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Totals({
  calc,
  currency,
  error,
  extra,
}: {
  calc: Calculation | null;
  currency: string;
  error?: string | null;
  extra?: { label: string; value: string }[];
}) {
  const money = useMoney();
  if (error) return <div role="alert" className="text-[12px] text-err">{error}</div>;
  const rows = calc
    ? [
        { label: 'Subtotal', value: money(calc.subtotal, currency) },
        { label: 'Discount', value: `−${money(addDecimals(calc.line_discount, calc.document_discount), currency)}` },
        ...calc.taxes.map((t) => ({
          label: `${calc.prices_include_tax ? 'Includes ' : ''}${t.code}`,
          value: money(t.tax, currency),
        })),
      ]
    : [];
  return (
    <div className="flex w-[320px] max-w-full flex-col gap-0.5">
      {rows.map((r) => (
        <div key={r.label} className="flex justify-between py-1 text-[12.5px] text-tx2">
          <span>{r.label}</span>
          <span className="tabular-nums">{r.value}</span>
        </div>
      ))}
      <div className="flex justify-between border-t border-bd2 py-1 text-[16px] font-bold text-tx">
        <span>Total</span>
        <span className="tabular-nums">{calc ? money(calc.total, currency) : '—'}</span>
      </div>
      {extra?.map((r) => (
        <div key={r.label} className="flex justify-between py-1 text-[12px] text-tx3">
          <span>{r.label}</span>
          <span className="tabular-nums">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

/** Exact sum of two decimal strings (no floating point). */
export function addDecimals(a: string, b: string): string {
  const scale = (v: string) => {
    const [w = '0', f = ''] = v.replace('-', '').split('.');
    const n = BigInt(w + f.padEnd(6, '0').slice(0, 6));
    return v.startsWith('-') ? -n : n;
  };
  const total = scale(a) + scale(b);
  const sign = total < 0n ? '-' : '';
  const abs = total < 0n ? -total : total;
  return `${sign}${abs / 1_000_000n}.${(abs % 1_000_000n).toString().padStart(6, '0')}`;
}
