'use client';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { FormDrawer, Screen, body } from '@/features/commerce/forms';
import { ListPanel, Primary } from '@/features/commerce/shared';
import { api } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import type { Party } from './types';

export function PartyDrawer({party,onClose}:{party?:Party;onClose:()=>void}) {
  const {can}=useAuth();
  return <FormDrawer title={party ? 'Edit participant' : 'Add founder / shareholder'} eyebrow="Company financial participants" initial={{name:party?.name ?? '',display_name:party?.display_name ?? '',kind:party?.kind ?? 'individual', email:party?.email ?? '',phone:party?.phone ?? '', country:party?.country ?? '',notes:party?.notes ?? '',joined:party?.joined ?? new Date().toLocaleDateString('en-CA'),left:party?.left ?? '',user_id:String(party?.user ?? ''),is_founder:party?.is_founder ?? true,is_shareholder:party?.is_shareholder ?? false,is_partner:party?.is_partner ?? false,is_active:party?.is_active ?? true}} onClose={onClose} fields={[
    {key:'name',label:'Full / organization name',required:true},{key:'display_name',label:'Display name'},
    {key:'kind',label:'Participant type',type:'select',options:[{value:'individual',label:'Individual'},{value:'organization',label:'Organization'}]},
    {key:'email',label:'Contact email',type:'email'},{key:'phone',label:'Phone'},{key:'country',label:'Country'},
    {key:'joined',label:'Participation starts',type:'date',required:true},{key:'left',label:'Participation ends (optional)',type:'date'},
    ...(can('users.manage') ? [{key:'user_id',label:'Linked ERP user ID (optional)',type:'number' as const,hint:'Link an existing account for authenticated consent. Leave blank for evidence-backed external attestations.'}] : []),
    {key:'is_founder',label:'Founder finance participant',type:'checkbox'},{key:'is_shareholder',label:'Shareholder / investor',type:'checkbox'}, {key:'is_partner',label:'Business partner',type:'checkbox'}, {key:'is_active',label:'Active',type:'checkbox'}, {key:'notes',label:'Notes',type:'textarea'},
  ]} onSave={v=>{const payload=body(v); if(!v.left) payload.left=null; if(!can('users.manage')) delete payload.user_id; return party ? api.patch(`/founders/parties/${party.id}/`,payload) : api.post('/founders/parties/',payload);}} />;
}

export function PartiesPage() {
  const {can}=useAuth(); const [edit,setEdit]=useState<Party|'new'|null>(null);
  return <Screen eyebrow="Ownership & Capital" title="Shareholders & partners" description="Manage founders, shareholders, and partners." actions={(can('ownership.manage') || can('founder.transactions.manage')) && <Button variant="primary" onClick={()=>setEdit('new')}>Add participant</Button>}>
    <ListPanel<Party> path="/founders/parties/" columns={[
      {key:'name',label:'Name',render:p=><Primary title={p.display_name || p.name} sub={p.email}/>}, {key:'kind',label:'Type',render:p=>[p.is_founder && 'Founder',p.is_shareholder && 'Shareholder',p.is_partner && 'Partner'].filter(Boolean).join(' · ') || p.kind},
      {key:'joined',label:'Joined',render:p=>p.joined},{key:'account',label:'ERP account',render:p=>p.user ? `User #${p.user}` : 'External · documented attestation'}, {key:'status',label:'Status',render:p=>p.is_active ? 'Active' : 'Inactive'},
      {key:'edit',label:'',render:p=>(can('ownership.manage') || can('founder.transactions.manage')) && <Button size="xs" onClick={()=>setEdit(p)}>Edit</Button>},
    ]}/>{edit && <PartyDrawer party={edit==='new' ? undefined : edit} onClose={()=>setEdit(null)}/>}
  </Screen>;
}
