import type { Metadata } from 'next';

import { FinancialSettingsPage } from '@/features/settings/business/BusinessPages';

export const metadata: Metadata = { title: 'Financial Settings' };

export default function Page() {
  return <FinancialSettingsPage />;
}
