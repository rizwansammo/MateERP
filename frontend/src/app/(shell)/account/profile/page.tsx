import type { Metadata } from 'next';

import { ProfilePage } from '@/features/settings/other/OtherPages';

export const metadata: Metadata = { title: 'My Profile' };

export default function Page() {
  return <ProfilePage />;
}
