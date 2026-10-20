import type { Metadata } from 'next';

import { PreferencesPage } from '@/features/settings/other/OtherPages';

export const metadata: Metadata = { title: 'Application Preferences' };

export default function Page() {
  return <PreferencesPage />;
}
