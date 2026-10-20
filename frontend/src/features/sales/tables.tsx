'use client';

import Link from 'next/link';

import { formatDate } from '@/lib/format';

import { type Column, ListPanel, Primary, StatusBadge, methodLabel, overdueDays, positive, useMoney } from '@/features/commerce/shared';
import type { InvoiceRow, Payment } from '@/features/commerce/types';

export const INVOICE_FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'draft', label: 'Drafts', query: 'status=draft' },
  { value: 'open', label: 'Open', query: 'status=open' },
  { value: 'overdue', label: 'Overdue', query: 'status=overdue' },
  { value: 'partial', label: 'Partially paid', query: 'status=partially_paid' },
  { value: 'paid', label: 'Paid', query: 'status=paid' },
  { value: 'void', label: 'Void', query: 'status=void' },
];

export function InvoiceTable({
  title,
  subtitle,
  customerId,
  projectId,
  hideCustomer = false,
  filters = false,
  status,
  defaultFilter,
}: {
  title?: string;
  subtitle?: string;
  customerId?: number;
  projectId?: number;
  hideCustomer?: boolean;
  filters?: boolean;
  status?: string;
  defaultFilter?: string;
}) {
  const money = useMoney();
  const params = new URLSearchParams();
  if (customerId) params.set('customer', String(customerId));
  if (projectId) params.set('project', String(projectId));
  if (status) params.set('status', status);
  const columns: Column<InvoiceRow>[] = [
    {
      key: 'no',
      label: 'Invoice',
      render: (i) => <Primary href={`/sales/invoices/${i.id}`} mono title={i.number ?? 'Draft'} sub={i.number ? undefined : `Created ${formatDate(i.created_at)}`} />,
    },
    ...(hideCustomer
      ? []
      : [
          {
            key: 'cu',
            label: 'Customer / project',
            render: (i: InvoiceRow) => <Primary title={i.customer_name} sub={i.project_reference ?? undefined} />,
          },
        ]),
    { key: 'date', label: 'Issued', render: (i) => (i.number ? formatDate(i.issue_date) : '—') },
    {
      key: 'due',
      label: 'Due',
      render: (i) => (
        <div className="flex flex-col">
          <span className={i.is_overdue ? 'text-err' : undefined}>{formatDate(i.due_date)}</span>
          {i.is_overdue && <span className="text-[11.5px] text-err">{overdueDays(i.due_date)} days overdue</span>}
        </div>
      ),
    },
    { key: 'st', label: 'Status', render: (i) => <StatusBadge status={i.status} overdue={i.is_overdue} /> },
    { key: 'total', label: 'Total', align: 'right', render: (i) => money(i.total, i.currency) },
    {
      key: 'out',
      label: 'Outstanding',
      align: 'right',
      render: (i) =>
        i.number && i.status !== 'void' ? (
          <span className={positive(i.outstanding) ? 'font-semibold' : 'text-tx3'}>{money(i.outstanding, i.currency)}</span>
        ) : (
          <span className="text-tx3">—</span>
        ),
    },
  ];
  return (
    <ListPanel<InvoiceRow>
      path={`/billing/invoices/${params.size ? `?${params}` : ''}`}
      title={title}
      subtitle={subtitle}
      filters={filters ? INVOICE_FILTERS : undefined}
      defaultFilter={defaultFilter}
      search="Search invoices…"
      empty="No invoices in this view."
      columns={columns}
      pageSize={filters ? 25 : 8}
    />
  );
}

export const PAYMENT_FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Pending verification', query: 'status=pending' },
  { value: 'verified', label: 'Verified', query: 'status=verified' },
  { value: 'rejected', label: 'Rejected', query: 'status=rejected' },
  { value: 'reversed', label: 'Reversed', query: 'status=reversed' },
];

export function PaymentTable({
  title,
  customerId,
  invoiceId,
  hideCustomer = false,
  filters = false,
}: {
  title?: string;
  customerId?: number;
  invoiceId?: number;
  hideCustomer?: boolean;
  filters?: boolean;
}) {
  const money = useMoney();
  const params = new URLSearchParams();
  if (customerId) params.set('customer', String(customerId));
  if (invoiceId) params.set('invoice', String(invoiceId));
  return (
    <ListPanel<Payment>
      path={`/billing/payments/${params.size ? `?${params}` : ''}`}
      title={title}
      filters={filters ? PAYMENT_FILTERS : undefined}
      search="Search payments…"
      empty="No payments yet."
      pageSize={filters ? 25 : 6}
      columns={[
        { key: 'no', label: 'Payment', render: (p) => <Primary href={`/sales/payments/${p.id}`} mono title={p.number} /> },
        { key: 'date', label: 'Date', render: (p) => formatDate(p.payment_date) },
        ...(hideCustomer
          ? []
          : [
              {
                key: 'cu',
                label: 'Customer / invoices',
                render: (p: Payment) => <Primary title={p.customer_name} sub={p.allocations.map((a) => a.invoice_number).join(', ') || 'Unallocated'} />,
              },
            ]),
        { key: 'm', label: 'Method / account', render: (p) => <Primary title={methodLabel(p.method)} sub={p.bank_account_name} /> },
        { key: 'ref', label: 'Reference', className: 'font-mono text-[12.5px]', render: (p) => p.reference || <span className="text-tx3">—</span> },
        { key: 'st', label: 'Status', render: (p) => <StatusBadge status={p.status} /> },
        { key: 'amt', label: 'Amount', align: 'right', render: (p) => <span className="font-semibold">{money(p.amount, p.currency)}</span> },
        {
          key: 'mr',
          label: 'Money receipt',
          render: (p) =>
            p.receipt ? (
              <Link href={`/sales/receipts?receipt=${p.receipt.id}`} className="font-mono text-[12.5px]">
                {p.receipt.number}
              </Link>
            ) : (
              <span className="text-tx3">{p.status === 'pending_verification' ? 'After verification' : '—'}</span>
            ),
        },
      ]}
    />
  );
}
