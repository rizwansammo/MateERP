import { notFound } from 'next/navigation';
import { PurchasesApp } from '@/features/purchases/PurchasesApp';
export default async function PurchasesPage({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = ['overview'] } = await params; const [section = 'overview', id] = path;
  if (!['overview', 'vendors', 'expenses', 'bills', 'payments', 'recurring', 'history', 'orders'].includes(section) || path.length > 2) notFound();
  if (id && (!['vendors', 'expenses', 'bills', 'payments'].includes(section) || !/^\d+$/.test(id))) notFound();
  return <PurchasesApp section={section} id={id} />;
}
