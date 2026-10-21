import { notFound } from 'next/navigation';
import { InventoryApp } from '@/features/operations/Inventory';
import { ModuleRoute } from '@/features/system/ModuleRoute';

export default async function InventoryPage({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = ['overview'] } = await params;
  const [section = 'overview', id] = path;
  if (!['overview', 'items', 'movements', 'locations', 'transfers', 'valuation'].includes(section) || path.length > 2 || (id && (section !== 'items' || !/^\d+$/.test(id)))) notFound();
  return <ModuleRoute itemId="inventory" group="Operations" subSlug={section}><InventoryApp section={section} id={id} /></ModuleRoute>;
}
