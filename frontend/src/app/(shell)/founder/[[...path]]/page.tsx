import { notFound } from 'next/navigation';
import { FoundersApp } from '@/features/founders/FoundersApp';
export default async function FounderPage({params}:{params:Promise<{path?:string[]}>}) {
  const {path=['overview']}=await params; const [section='overview',id]=path;
  if(!['overview','contributions','expenses','sharing','settlements','loans','reimbursements','statements'].includes(section) || path.length>2 || id && (!/^\d+$/.test(id) || !['contributions','expenses','reimbursements','settlements'].includes(section))) notFound();
  return <FoundersApp section={section} id={id}/>;
}
