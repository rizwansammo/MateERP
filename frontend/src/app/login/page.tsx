import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AuthLayout } from '@/features/auth/AuthLayout';
import { LoginForm } from '@/features/auth/LoginForm';
import { safeNext } from '@/lib/auth/redirect';
import { getServerSession } from '@/lib/auth/server';

export const metadata: Metadata = { title: 'Sign in' };

interface Props {
  searchParams: Promise<{ next?: string; reason?: string }>;
}

export default async function LoginPage({ searchParams }: Props) {
  const { next, reason } = await searchParams;
  const session = await getServerSession();
  if (session?.authenticated && session.user) {
    redirect(
      session.user.must_change_password
        ? '/account/password'
        : safeNext(next, session.user.preferences.landing_page ?? '/dashboard'),
    );
  }
  return (
    <AuthLayout>
      <LoginForm next={next ? safeNext(next) : null} expired={reason === 'expired'} />
    </AuthLayout>
  );
}
