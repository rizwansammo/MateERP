import type { Metadata } from 'next';
import { Suspense } from 'react';

import { Flash } from '@/features/system/Flash';
import { ExecutiveDashboard } from '@/features/operations/Dashboard';

export const metadata: Metadata = { title: 'Dashboard' };

export default function DashboardPage() {
  return (
    <>
      <Suspense>
        <Flash />
      </Suspense>
      <ExecutiveDashboard />
    </>
  );
}
