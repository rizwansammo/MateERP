import { notFound } from 'next/navigation';
import { SalesApp } from '@/features/sales/SalesApp';
export default async function SalesPage({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = ['overview'] } = await params;
  const [section = 'overview', id, action] = path;
  if (!['overview', 'customers', 'orders', 'invoices', 'payments', 'receipts', 'credits', 'recurring', 'projects', 'setup'].includes(section) || path.length > 3) notFound();
  if (id && (!['customers', 'orders', 'invoices', 'payments', 'receipts', 'projects'].includes(section) || !/^\d+$/.test(id) && !(section === 'invoices' && id === 'new'))) notFound();
  if (action && !(section === 'invoices' && id !== 'new' && action === 'edit')) notFound();
  return <SalesApp section={section} id={id} edit={action === 'edit'} />;
}
