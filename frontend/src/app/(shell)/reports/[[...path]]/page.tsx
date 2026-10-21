import { notFound } from 'next/navigation';
import { ReportsApp } from '@/features/operations/Reports';

export default async function ReportsPage({params}:{params:Promise<{path?:string[]}>}) {
  const {path=[]}=await params;
  if(path.length>1||path[0]&&!['pnl','bs','tb','ledger','cash-flow','cf','income','expense','ar','ap','customer','product','vendors','locations','low-stock','receiving','history','recurring','bank','tax'].includes(path[0]))notFound();
  return <ReportsApp which={path[0]} />;
}
