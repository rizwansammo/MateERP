import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AuthLayout } from '@/features/auth/AuthLayout';
import { BackendUnavailable } from '@/features/auth/BackendUnavailable';
import { PasswordForm } from '@/features/auth/PasswordForm';
import { loginUrl } from '@/lib/auth/redirect';
import { getServerSession } from '@/lib/auth/server';

export const metadata: Metadata = { title: 'Change password' };

export default async function PasswordPage() {
  const session = await getServerSession();
  if (session === null) return <BackendUnavailable />;
  if (!session.authenticated || !session.user) redirect(loginUrl('/account/password', 'expired'));
  return (
    <AuthLayout>
      <PasswordForm forced={session.user.must_change_password} displayName={session.user.display_name} />
    </AuthLayout>
  );
}
