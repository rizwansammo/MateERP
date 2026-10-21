'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { FormDrawer } from '@/features/commerce/forms';
import { ListPanel, useApi, useMoney } from '@/features/commerce/shared';
import type { Project } from '@/features/commerce/types';
import { api } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';

export interface SpendingLine { id: number; journal_id: string; number: string; date: string; account_code: string; description: string; base_debit: string; base_credit: string; analytical_cost_center: string | null; analytical_project: string | null }

export function CostClassification({ journalId }: { journalId?: string }) {
  const { can } = useAuth(); const money = useMoney(); const [edit,setEdit] = useState<SpendingLine | null>(null);
  const centers = useApi<Page<{ id: number; code: string; name: string; is_active: boolean }>>(edit ? '/budgeting/cost-centers/?page_size=100' : null);
  const projects = useApi<Page<Project>>(edit ? '/sales/projects/?page_size=100' : null);
  return <><ListPanel<SpendingLine> title="Posted spending classifications" path={`/budgeting/spending/${journalId ? `?journal_id=${journalId}` : ''}`} search="Search journal, account or description…" columns={[
    { key:'source',label:'Posted source',render:l=>`${l.number} · ${l.account_code}` }, { key:'description',label:'Description',render:l=>l.description },
    { key:'debit',label:'Base debit',align:'right',render:l=>money(l.base_debit) }, { key:'credit',label:'Base credit',align:'right',render:l=>money(l.base_credit) },
    { key:'center',label:'Cost center',render:l=>l.analytical_cost_center ? `#${l.analytical_cost_center}` : 'Unassigned' },
    { key:'action',label:'Classification',render:l=>can('budgets.manage') && <Button size="xs" onClick={()=>setEdit(l)}>Classify spending</Button> },
  ]} />{edit && <FormDrawer title="Classify posted spending" eyebrow={`${edit.number} · ${edit.account_code}`} onClose={()=>setEdit(null)}
    description="Adds an audited analytical version. The original journal, financial project identity and monetary amounts remain unchanged. Asset reclassification and depreciation inherit acquisition attribution unless explicitly classified."
    initial={{ cost_center_id:edit.analytical_cost_center ?? '',project_id:edit.analytical_project ?? '',reason:'' }}
    fields={[{key:'cost_center_id',label:'Cost center',type:'select',options:[{value:'',label:'Unassigned'},...(centers.data?.results??[]).filter(c=>c.is_active).map(c=>({value:String(c.id),label:`${c.code} · ${c.name}`}))]},
      {key:'project_id',label:'Analytical project scope',type:'select',options:[{value:'',label:'Unassigned'},...(projects.data?.results??[]).map(p=>({value:String(p.id),label:p.name}))]},
      {key:'reason',label:'Classification authority and rationale',type:'textarea',required:true}]}
    onSave={v=>api.post('/budgeting/classifications/',{line_id:edit.id,cost_center_id:v.cost_center_id ? Number(v.cost_center_id):null,project_id:v.project_id ? Number(v.project_id):null,reason:v.reason})}>
    <ListPanel<{id:number;version:number;reason:string;created_at:string}> path={`/budgeting/classifications/?line_id=${edit.id}`} title="Retained classification history" columns={[
      {key:'version',label:'Version',render:t=>`v${t.version}`},{key:'reason',label:'Reason',render:t=>t.reason},
    ]} />
  </FormDrawer>}</>;
}
