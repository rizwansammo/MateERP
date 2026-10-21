import { notFound } from 'next/navigation';
import { AssetsApp } from '@/features/operations/Assets';
import { ModuleRoute } from '@/features/system/ModuleRoute';

export default async function AssetsPage({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = ['register'] } = await params;
  const [section = 'register', id] = path;
  if (!['register','details','depreciation','disposal'].includes(section) || path.length > 2) notFound();
  if (id && (!['register','details'].includes(section) || !/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id))) notFound();
  return <ModuleRoute itemId="assets" group="Operations" subSlug={section}><AssetsApp section={section} id={id} /></ModuleRoute>;
}
