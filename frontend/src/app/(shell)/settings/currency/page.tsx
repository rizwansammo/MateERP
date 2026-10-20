import type { Metadata } from 'next';

import { CurrencySettingsPage } from '@/features/settings/business/BusinessPages';

export const metadata: Metadata = { title: 'Currency Settings' };

export default function Page() {
  return <CurrencySettingsPage />;
}
