'use client';

import type { ReactNode } from 'react';

import { Restricted } from '@/components/ui/Restricted';
import { useAuth } from '@/lib/auth/AuthProvider';

/**
 * Shows a restricted card when the user holds none of ``anyOf``. This only
 * improves the experience: every API call behind the page is authorised by
 * the server independently.
 */
export function Gate({ anyOf, children }: { anyOf: string[]; children: ReactNode }) {
  const { canAny, user } = useAuth();
  if (canAny(...anyOf)) return <>{children}</>;
  return (
    <Restricted title="Access restricted" action={{ label: 'Go to dashboard', href: '/dashboard' }}>
      Your role ({user.role?.name ?? 'no role'}) does not include the permission needed for this
      page. Ask an administrator to update your role.
    </Restricted>
  );
}
