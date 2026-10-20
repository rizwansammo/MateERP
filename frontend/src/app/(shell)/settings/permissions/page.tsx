import type { Metadata } from 'next';
import { Suspense } from 'react';

import { PermissionsPage } from '@/features/settings/permissions/PermissionMatrix';

export const metadata: Metadata = { title: 'Permissions' };

export default function Page() {
  return (
    <Suspense>
      <PermissionsPage />
    </Suspense>
  );
}
