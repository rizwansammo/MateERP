'use client';
import { Gate, ListPanel, Primary, StatusBadge } from '@/features/commerce/shared';
import { Screen } from '@/features/commerce/forms';
import type { Proposal } from './types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { PartiesPage } from '@/features/founders/Parties';
import { OwnershipPage, OwnershipDetail } from './Ownership';

export function OwnershipApp({section,id}:{section:string;id?:string}) {
  const {canAny}=useAuth();
  if(!id && !canAny('ownership.view','ownership.manage')) return <Gate allow={canAny('ownership.approve','ownership.consent')} what="ownership records"><Screen eyebrow="Ownership & Capital" title="Ownership requests" description="Only proposals you are authorized to review or consent to are returned by the server."><ListPanel<Proposal> path="/ownership/proposals/" title="Authorized ownership requests" columns={[{key:'title',label:'Proposal',render:p=><Primary title={p.title} href={`/ownership/history/${p.id}`} sub={p.effective_date}/>},{key:'status',label:'Status',render:p=><StatusBadge status={p.status}/>} ]}/></Screen></Gate>;
  return <Gate allow={canAny('ownership.view','ownership.manage','ownership.approve','ownership.consent')} what="ownership records">{id ? <OwnershipDetail id={id}/> : section==='shareholders' ? <PartiesPage/> : <OwnershipPage section={section}/>}</Gate>;
}
