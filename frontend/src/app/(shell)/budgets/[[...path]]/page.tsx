import { notFound } from 'next/navigation';
import { BudgetsApp } from '@/features/operations/Budgets';
import { ModuleRoute } from '@/features/system/ModuleRoute';

export default async function BudgetsPage({params}:{params:Promise<{path?:string[]}>}) {
  const {path=['budgets']}=await params;
  const [section='budgets',id]=path;
  if(!['budgets','costcenters','comparison'].includes(section)||path.length>2)notFound();
  if(id&&(section!=='budgets'||!/^\d+$/.test(id)))notFound();
  return <ModuleRoute itemId="budgets" group="Finance" subSlug={section}><BudgetsApp section={section} id={id} /></ModuleRoute>;
}
