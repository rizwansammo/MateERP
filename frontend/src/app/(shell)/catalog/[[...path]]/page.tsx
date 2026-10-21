import { notFound } from 'next/navigation';
import { CatalogApp } from '@/features/operations/Catalog';

export default async function CatalogPage({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = ['products'] } = await params;
  const [section = 'products', id] = path;
  if (!['products', 'services', 'pricing'].includes(section) || path.length > 2 || (id && !/^\d+$/.test(id))) notFound();
  return <CatalogApp section={section} id={id} />;
}
