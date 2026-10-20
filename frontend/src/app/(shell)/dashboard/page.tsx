import type { Metadata } from 'next';

import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { HealthPanel } from '@/features/system/HealthPanel';
import { PlannedNotice } from '@/features/system/PlannedModule';
import { findNavItem } from '@/lib/navigation';

export const metadata: Metadata = { title: 'Dashboard' };

const dashboard = findNavItem('dashboard');

export default function DashboardPage() {
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        description="Live status of this MateERP installation. Executive financial KPIs appear here once the accounting and reporting modules are delivered."
      />
      <HealthPanel />
      <PlannedNotice item={dashboard} />
    </PageContainer>
  );
}
