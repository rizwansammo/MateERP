import { notFound } from 'next/navigation';
import { FoundersApp } from '@/features/founders/FoundersApp';
import { ModuleRoute } from '@/features/system/ModuleRoute';
export default async function FounderPage({params}:{params:Promise<{path?:string[]}>}) {
  const {path=['overview']}=await params; const [section='overview',id]=path;
  if(!['overview','contributions','expenses','sharing','settlements','loans','reimbursements','statements'].includes(section) || path.length>2 || id && (!/^\d+$/.test(id) || !['contributions','expenses','reimbursements','settlements'].includes(section))) notFound();
  return <ModuleRoute itemId="founder" group="Finance" subSlug={section}><FoundersApp section={section} id={id}/></ModuleRoute>;
}
