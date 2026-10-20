import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { AppShell } from '@/components/shell/AppShell';
import { Toaster } from '@/components/ui/Toast';
import { BackendUnavailable } from '@/features/auth/BackendUnavailable';
import { AuthProvider } from '@/lib/auth/AuthProvider';
import { loginUrl } from '@/lib/auth/redirect';
import { getServerSession, requestedPath } from '@/lib/auth/server';

/** Every page in this group requires a valid session, checked on the server. */
export default async function ShellLayout({ children }: { children: ReactNode }) {
  const session = await getServerSession();
  if (session === null) return <BackendUnavailable />;
  if (!session.authenticated || !session.user) {
    redirect(loginUrl(await requestedPath(), 'expired'));
  }
  if (session.user.must_change_password) redirect('/account/password');

  return (
    <AuthProvider initialUser={session.user}>
      <AppShell>{children}</AppShell>
      <Toaster />
    </AuthProvider>
  );
}
