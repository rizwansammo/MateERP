import type { Metadata } from 'next';

import { PlannedSettingsPage } from '@/features/settings/other/OtherPages';

export const metadata: Metadata = { title: 'Integration Settings' };

export default function Page() {
  return (
    <PlannedSettingsPage
      title="Integration settings"
      phase={7}
      description="MateERP works fully standalone. Optional connectors to other NetaMate products and external services are planned; nothing connects today."
    />
  );
}
