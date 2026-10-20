import type { Metadata } from 'next';

import { TaxSettingsPage } from '@/features/settings/business/BusinessPages';

export const metadata: Metadata = { title: 'Tax Settings' };

export default function Page() {
  return <TaxSettingsPage />;
}
