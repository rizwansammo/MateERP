'use client';

import { Restricted } from '@/components/ui/Restricted';
import { useModules } from '@/lib/api/hooks';
import { useAuth } from '@/lib/auth/AuthProvider';
import { canAccess, findNavItem, isVisible } from '@/lib/navigation';

import { PlannedModule } from './PlannedModule';

interface Props {
  itemId: string;
  group: string;
  subSlug: string | null;
}

/**
 * A planned business module route. Disabled optional modules and modules
 * outside the user's role show the prototype's restricted card instead.
 */
export function ModuleRoute({ itemId, group, subSlug }: Props) {
  const { can, user } = useAuth();
  const { states, loading } = useModules();
  const item = findNavItem(itemId);
  const sub = item.subs?.find((s) => s.slug === subSlug) ?? null;

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
  return <PlannedModule item={item} group={group} current={sub} />;
}
