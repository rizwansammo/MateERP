'use client';
import Link from 'next/link';
import { Banner } from '@/components/ui/Banner';
import { InfoPanel } from '@/components/ui/InfoPanel';
import { errorMessage, api } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { Screen } from '@/features/commerce/forms';
import { ListPanel, Primary, StatusBadge, PdfState, Card, useApi, useMoney } from '@/features/commerce/shared';
import type { Receipt } from '@/features/commerce/types';
import { ReceiptPaper } from './preview';

export function ReceiptsPage() {
  const money = useMoney();
  return <Screen eyebrow="Sales & Billing" title="Money receipts" description="Official receipts are created only when a customer payment is verified. Each receipt preserves its issued branding and PDF.">
    <ListPanel<Receipt> path="/billing/receipts/" empty="No official money receipts yet." columns={[
      { key: 'no', label: 'Receipt', render: r => <Primary mono href={`/sales/receipts/${r.id}`} title={r.number} /> },
      { key: 'date', label: 'Issued', render: r => formatDate(r.issue_date) },
      { key: 'customer', label: 'Customer', render: r => r.customer_name },
      { key: 'payment', label: 'Payment', render: r => <Link href={`/sales/payments/${r.payment_id}`}>{r.payment_number}</Link> },
      { key: 'status', label: 'Status', render: r => <StatusBadge status={r.status} /> },
      { key: 'amount', label: 'Amount', align: 'right', render: r => money(r.amount, r.currency) },
      { key: 'pdf', label: 'PDF', render: r => r.pdf_status === 'ready' && r.pdf_url ? <a href={r.pdf_url} target="_blank" rel="noreferrer">Open PDF</a> : r.pdf_status },
    ]} />
  </Screen>;
}
export function ReceiptDetail({ id }: { id: string }) {
  const query = useApi<Receipt>(`/billing/receipts/${id}/`);
  const { can } = useAuth();
  const money = useMoney();
  const r = query.data;
  return <Screen eyebrow="Money receipt" title={r?.number ?? 'Money receipt'} description="Issued payment confirmation. A cancelled receipt remains available as historical evidence."
    actions={r && <PdfState status={r.pdf_status} url={r.pdf_url} error={r.pdf_error} canRetry={can('payments.approve') || can('documents.manage')} onRetry={() => api.post(`/billing/receipts/${r.id}/pdf/`)} />}>
    {Boolean(query.error) && <Banner tone="err">{errorMessage(query.error)}</Banner>}
    {r ? <><InfoPanel title="Receipt details" rows={[
      { label: 'Customer', value: r.customer_name }, { label: 'Amount', value: money(r.amount, r.currency) },
      { label: 'Date', value: formatDate(r.issue_date) }, { label: 'Status', value: <StatusBadge status={r.status} /> },
      { label: 'Payment', value: <Link href={`/sales/payments/${r.payment_id}`}>{r.payment_number}</Link> },
      { label: 'Branding version', value: String(r.branding_version) },
    ]} /><Card title="Historical receipt preview" subtitle="The stored official PDF is the authoritative issued document."><div className="overflow-auto bg-sf2 p-4"><ReceiptPaper snapshot={r.snapshot} number={r.number} version={r.branding_version} scale={0.85} /></div></Card></> : !query.error && <div className="text-tx3">Loading receipt…</div>}
  </Screen>;
}
