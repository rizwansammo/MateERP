import { notFound } from 'next/navigation';
import { OwnershipApp } from '@/features/ownership/OwnershipApp';
import { ModuleRoute } from '@/features/system/ModuleRoute';
export default async function OwnershipPage({params}:{params:Promise<{path?:string[]}>}) {
  const {path=['shareholders']}=await params; const [section='shareholders',id]=path;
  if(!['shareholders','overview','capital','transfers','issuance','history'].includes(section) || path.length>2 || id && (!/^\d+$/.test(id) || section!=='history')) notFound();
  return <ModuleRoute itemId="ownership" group="Finance" subSlug={section}><OwnershipApp section={section} id={id}/></ModuleRoute>;
}
