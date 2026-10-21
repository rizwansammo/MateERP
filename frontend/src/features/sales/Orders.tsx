'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Choice';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field } from '@/components/ui/Field';
import { Input, Select } from '@/components/ui/Input';
import { Cell, DialogActions, DialogFooter, Drawer, FormGrid } from '@/components/ui/Overlay';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { useUnsavedGuard } from '@/lib/forms';

import { useConfig } from '@/features/accounting/shared';
import { type EditLine, LinesEditor, Totals, blankLine, toEditLines, toPayload, useCalculation } from '@/features/commerce/lines';
import { Screen } from '@/features/commerce/forms';
import { ListPanel, Primary, StatusBadge, act, refreshCommerce, today, useApi, useMoney } from '@/features/commerce/shared';
import type { Customer, Invoice, SalesOrder } from '@/features/commerce/types';

const EYEBROW = 'Sales & Billing';

function OrderDrawer({ order, onClose }: { order?: SalesOrder; onClose: () => void }) {
  const config = useConfig();
  const customers = useApi<Page<Customer>>('/sales/customers/?status=active&page_size=100');
  const [customerId, setCustomerId] = useState(order ? String(order.customer_id) : '');
  const [currency, setCurrency] = useState(order?.currency ?? '');
  const [date, setDate] = useState(order?.order_date ?? today());
  const [title, setTitle] = useState(order?.title ?? '');
  const [reference, setReference] = useState(order?.customer_reference ?? '');
  const [inclusive, setInclusive] = useState(order?.prices_include_tax ?? false);
  const [lines, setLines] = useState<EditLine[]>(order ? toEditLines(order.lines, 'revenue_account_id') : [blankLine()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [discard, setDiscard] = useState(false);
  const signature = JSON.stringify([customerId, currency, date, title, reference, inclusive, lines]);
  const [initialSignature] = useState(signature);
  const dirty = signature !== initialSignature;
  useUnsavedGuard(dirty && !busy);
  const close = () => { if (!busy) { if (dirty) setDiscard(true); else onClose(); } };
  const calc = useCalculation({ currency, date, lines, pricesIncludeTax: inclusive });
  const save = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    const data = {
      customer_id: Number(customerId),
      currency,
      order_date: date,
      title,
      customer_reference: reference,
      prices_include_tax: inclusive,
      lines: toPayload(lines, 'revenue_account_id').map(l => ({ description: l.description, quantity: l.quantity, unit_price: l.unit_price, discount_type: l.discount_type, discount_value: l.discount_value, tax_code_id: l.tax_code_id, item_id: l.item_id })),
      ...(order ? { revision: order.revision } : {}),
    };
    try {
      await act(() => (order ? api.patch(`/sales/orders/${order.id}/`, data) : api.post('/sales/orders/', data)), 'Sales order saved');
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <><Drawer
      open
      title={order ? `Edit ${order.number}` : 'New sales order'}
      eyebrow={EYEBROW}
      description="A sales order records what the customer ordered. It creates no receivable; invoices issued from it do."
      width={1000}
      onClose={close}
      footer={
        <DialogFooter>
          {error && <Banner tone="err">{error}</Banner>}
          <DialogActions>
            <Button disabled={busy} onClick={close}>
              Cancel
            </Button>
            <Button variant="primary" disabled={busy || !customerId} onClick={() => void save()}>
              {busy ? 'Saving…' : 'Save sales order'}
            </Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      <FormGrid>
        <Cell w="half">
          <Field label="Customer" htmlFor="so-customer" required>
            <Select id="so-customer" aria-label="Customer" value={customerId} onChange={(e) => { setCustomerId(e.target.value); const c = customers.data?.results.find((x) => String(x.id) === e.target.value); if (c) setCurrency(c.currency); }}>
              <option value="">Select customer</option>
              {customers.data?.results.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
        </Cell>
        <Cell w="third">
          <Field label="Order date" htmlFor="so-date">
            <Input id="so-date" type="date" aria-label="Order date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
        </Cell>
        <Cell w="third">
          <Field label="Currency" htmlFor="so-currency">
            <Select id="so-currency" aria-label="Currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {(config.data?.enabled_currencies ?? []).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </Field>
        </Cell>
        <Cell w="half">
          <Field label="Order title" htmlFor="so-title">
            <Input id="so-title" aria-label="Order title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
        </Cell>
        <Cell w="half">
          <Field label="Customer PO reference" htmlFor="so-ref">
            <Input id="so-ref" aria-label="Customer PO reference" value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
        </Cell>
        <Cell w="full">
          <div className="border border-bd">
            <LinesEditor lines={lines} onChange={setLines} currency={currency} date={date} pricesIncludeTax={inclusive} calc={calc.result} accountKind="revenue" />
            <div className="flex flex-wrap items-start justify-between gap-3 px-3 py-3">
              <div className="flex flex-col gap-3">
                <Button size="sm" icon="add" onClick={() => setLines([...lines, blankLine()])}>
                  Add line
                </Button>
                <Checkbox checked={inclusive} onChange={setInclusive} label="Prices include tax" />
              </div>
              <Totals calc={calc.result} currency={currency} error={calc.error} />
            </div>
          </div>
        </Cell>
      </FormGrid>
    </Drawer>
    <ConfirmDialog open={discard} title="Discard unsaved order changes?" confirmLabel="Discard" danger onCancel={() => setDiscard(false)} onConfirm={onClose} /></>
  );
}

export function OrdersPage() {
  const { can } = useAuth();
  const router = useRouter();
  const money = useMoney();
  const [edit, setEdit] = useState<SalesOrder | 'new' | null>(null);
  const [cancel, setCancel] = useState<SalesOrder | null>(null);
  const convert = async (o: SalesOrder) => {
    try {
      const inv = await api.post<Invoice>('/billing/invoices/from-source/', { order_id: o.id });
      refreshCommerce();
      toast(`Draft invoice created from ${o.number}`);
      router.push(`/sales/invoices/${inv.id}/edit`);
    } catch (e) {
      toast(errorMessage(e), 'err');
    }
  };
  return (
    <Screen
      eyebrow={EYEBROW}
      title="Sales orders"
      description="Confirm what the customer ordered, then convert it into an invoice in one step. Orders never post to the ledger."
      actions={
        can('sales.manage') && (
          <Button variant="primary" icon="add" onClick={() => setEdit('new')}>
            New sales order
          </Button>
        )
      }
    >
      <ListPanel<SalesOrder>
        path="/sales/orders/"
        search="Search orders…"
        filters={[
          { value: 'all', label: 'All' },
          { value: 'draft', label: 'Drafts', query: 'status=draft' },
          { value: 'confirmed', label: 'Confirmed', query: 'status=confirmed' },
          { value: 'partial', label: 'Partially invoiced', query: 'status=partially_invoiced' },
          { value: 'invoiced', label: 'Fully invoiced', query: 'status=invoiced' },
          { value: 'cancelled', label: 'Cancelled', query: 'status=cancelled' },
        ]}
        empty="No sales orders."
        columns={[
          { key: 'no', label: 'Order', render: (o) => <Primary mono title={o.number} href={`/sales/orders/${o.id}`} /> },
          { key: 'cu', label: 'Customer', render: (o) => o.customer_name },
          { key: 'title', label: 'Title', render: (o) => <Primary title={o.title || '—'} sub={o.customer_reference ? `PO ${o.customer_reference}` : undefined} /> },
          { key: 'date', label: 'Date', render: (o) => formatDate(o.order_date) },
          { key: 'st', label: 'Status', render: (o) => <StatusBadge status={o.status} /> },
          { key: 'total', label: 'Total', align: 'right', render: (o) => money(o.total, o.currency) },
          { key: 'ccy', label: 'Currency', className: 'font-mono', render: (o) => o.currency },
          {
            key: 'act',
            label: '',
            align: 'right',
            render: (o) => (
              <div className="flex justify-end gap-1.5">
                {o.status === 'draft' && can('sales.manage') && (
                  <>
                    <Button size="xs" onClick={() => setEdit(o)}>
                      Edit
                    </Button>
                    <Button size="xs" variant="primary" onClick={() => void act(() => api.post(`/sales/orders/${o.id}/confirm/`), `${o.number} confirmed`).catch((e) => toast(errorMessage(e), 'err'))}>
                      Confirm
                    </Button>
                  </>
                )}
                {(o.status === 'confirmed' || o.status === 'partially_invoiced') && can('invoices.create') && (
                  <Button size="xs" variant="primary" icon="arrow_forward" onClick={() => void convert(o)}>
                    Convert to invoice
                  </Button>
                )}
                {(o.status === 'draft' || o.status === 'confirmed') && can('sales.manage') && (
                  <Button size="xs" variant="ghost" onClick={() => setCancel(o)}>
                    Cancel
                  </Button>
                )}
              </div>
            ),
          },
        ]}
      />
      {edit && <OrderDrawer order={edit === 'new' ? undefined : edit} onClose={() => setEdit(null)} />}
      <ConfirmDialog
        open={Boolean(cancel)}
        title={`Cancel ${cancel?.number}?`}
        confirmLabel="Cancel order"
        danger
        reason="required"
        onCancel={() => setCancel(null)}
        onConfirm={async (reason) => {
          await act(() => api.post(`/sales/orders/${cancel!.id}/cancel/`, { reason }), 'Order cancelled');
          setCancel(null);
        }}
      >
        Orders with invoices (including drafts) cannot be cancelled.
      </ConfirmDialog>
    </Screen>
  );
}
