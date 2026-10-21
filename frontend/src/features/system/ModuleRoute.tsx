'use client';

import type { ReactNode } from 'react';
import { Button } from '@/components/ui/Button';
import { Restricted } from '@/components/ui/Restricted';
import { Spinner } from '@/components/ui/Spinner';
import { useModules } from '@/lib/api/hooks';
import { errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { canAccess, findNavItem, isVisible } from '@/lib/navigation';

import { PlannedModule } from './PlannedModule';

interface Props {
  itemId: string;
  group: string;
  subSlug: string | null;
  children?: ReactNode;
}

/**
 * Shared guard for working and planned module routes. Do not mount child
 * controls until the installation's module configuration has loaded.
 */
export function ModuleRoute({ itemId, group, subSlug, children }: Props) {
  const { can, user } = useAuth();
  const { states, loading, error, refresh } = useModules();
  const item = findNavItem(itemId);
  const sub = item.subs?.find((s) => s.slug === subSlug) ?? null;

  if (loading) return <div className="p-7"><Spinner /></div>;
  if (error) return <Restricted title="Module settings unavailable">
    {errorMessage(error)} <Button size="sm" onClick={()=>void refresh()}>Try again</Button>
  </Restricted>;

  if (!loading && (!isVisible(item, states) || (sub && !isVisible(sub, states)))) {
    return (
      <Restricted title={`${sub?.label ?? item.label} is disabled`} action={{ label: 'Open module settings', href: '/settings/modules' }}>
        This optional module is hidden for this installation. Historical records are retained and it
        can be shown again from Settings → Modules.
      </Restricted>
    );
  }
  if (!canAccess(item, can)) {
    return (
      <Restricted title="Access restricted" action={{ label: 'Go to dashboard', href: '/dashboard' }}>
        Your role ({user.role?.name ?? 'no role'}) does not include access to {item.label}. Ask an
        administrator to update your permissions.
      </Restricted>
    );
  }
  return children ?? <PlannedModule item={item} group={group} current={sub} />;
}
