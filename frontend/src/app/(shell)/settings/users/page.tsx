import type { Metadata } from 'next';

import { UsersPage } from '@/features/settings/users/UsersPage';

export const metadata: Metadata = { title: 'Users & Roles' };

export default function Page() {
  return <UsersPage />;
}
