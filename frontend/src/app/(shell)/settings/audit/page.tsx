import type { Metadata } from 'next';

import { AuditPage } from '@/features/settings/audit/AuditPage';

export const metadata: Metadata = { title: 'Audit Logs' };

export default function Page() {
  return <AuditPage />;
}
