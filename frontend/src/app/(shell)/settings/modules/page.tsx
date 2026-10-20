import type { Metadata } from 'next';

import { ModulesPage } from '@/features/settings/modules/ModulesPage';

export const metadata: Metadata = { title: 'Modules' };

export default function Page() {
  return <ModulesPage />;
}
