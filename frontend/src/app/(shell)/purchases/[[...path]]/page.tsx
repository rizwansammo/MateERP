import { notFound } from 'next/navigation';
import { PurchasesApp } from '@/features/purchases/PurchasesApp';
import { ModuleRoute } from '@/features/system/ModuleRoute';
export default async function PurchasesPage({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = ['overview'] } = await params; const [section = 'overview', id] = path;
  if (!['overview', 'vendors', 'expenses', 'bills', 'payments', 'recurring', 'history', 'orders', 'onboarding'].includes(section) || path.length > 2) notFound();
  if (id && (!['vendors', 'expenses', 'bills', 'payments', 'orders'].includes(section) || !/^\d+$/.test(id))) notFound();
  const content=<PurchasesApp section={section} id={id} />;
  return section==='orders'?<ModuleRoute itemId="purchases" group="Finance" subSlug="orders">{content}</ModuleRoute>:content;
}
