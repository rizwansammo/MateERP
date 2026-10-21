'use client';
import { Gate } from '@/features/commerce/shared';
import { useAuth } from '@/lib/auth/AuthProvider';
import { CorporateDetail, CorporatePage } from './Corporate';
import { FounderOverviewPage, LoansPage } from './Overview';
import { SettlementsPage, SettlementDetail } from './Personal';
import { SharingPage } from './Sharing';

export function FoundersApp({section,id}:{section:string;id?:string}) {
  const {can}=useAuth(); const allow=section==='settlements' ? can('founder.personal.view') : can('founder.view');
  return <Gate allow={allow} what="founder finance"><>{section==='settlements' ? id ? <SettlementDetail id={id}/> : <SettlementsPage/> : id ? <CorporateDetail id={id}/> : section==='overview' || section==='statements' ? <FounderOverviewPage statement={section==='statements'}/> : section==='sharing' ? <SharingPage/> : section==='loans' ? <LoansPage/> : <CorporatePage section={section}/>}</></Gate>;
}
