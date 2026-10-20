import type { Metadata } from 'next';

import { PlannedSettingsPage } from '@/features/settings/other/OtherPages';

export const metadata: Metadata = { title: 'Notification Preferences' };

export default function Page() {
  return (
    <PlannedSettingsPage
      title="Notification preferences"
      phase={4}
      description="Choose which reminders appear in the notification centre — overdue invoices, bills, renewals and more. Approval requests already appear in the header."
    />
  );
}
