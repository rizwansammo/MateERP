'use client';

import { useRouter } from 'next/navigation';
import { type FormEvent, useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Choice';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { ApiError, apiRequest } from '@/lib/api/client';
import type { CurrentUser } from '@/lib/api/types';
import { safeNext } from '@/lib/auth/redirect';

import { AuthCard } from './AuthLayout';
import { PasswordInput } from './PasswordInput';

interface LoginFormProps {
  next: string | null;
  expired: boolean;
}

export function LoginForm({ next, expired }: LoginFormProps) {
  const router = useRouter();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ identifier?: string; password?: string }>({});

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    const errors: typeof fieldErrors = {};
    if (!identifier.trim()) errors.identifier = 'Enter your username or email.';
    if (!password) errors.password = 'Enter your password.';
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;

    setSubmitting(true);
    setError(null);
    try {
      const user = await apiRequest<CurrentUser>('/auth/login/', {
        method: 'POST',
        body: { identifier: identifier.trim(), password, remember },
        quiet401: true,
      });
      const destination = user.must_change_password
        ? '/account/password'
        : safeNext(next, user.preferences.landing_page ?? '/dashboard');
      // The successful response has set the session cookie. Navigating loads
      // the protected server layout; refreshing here can cancel that navigation.
      router.replace(destination);
    } catch (err) {
      setPassword('');
      if (err instanceof ApiError && err.kind === 'http') setError(err.message);
      else if (err instanceof ApiError) setError('The MateERP server could not be reached. Try again shortly.');
      else setError('Sign-in failed. Try again.');
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      eyebrow="Sign in"
      title="Welcome to MateERP"
      description="Use the account your administrator created for you."
    >
      {expired && !error && (
        <Banner tone="info" compact>
          Your session has ended. Sign in again to continue.
        </Banner>
      )}
      {error && (
        <Banner tone="err" compact>
          {error}
        </Banner>
      )}
      <form noValidate onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label="Username or email" htmlFor="login-identifier" error={fieldErrors.identifier}>
          <Input
            id="login-identifier"
            name="username"
            autoComplete="username"
            autoFocus
            value={identifier}
            invalid={Boolean(fieldErrors.identifier)}
            onChange={(e) => setIdentifier(e.target.value)}
          />
        </Field>
        <Field label="Password" htmlFor="login-password" error={fieldErrors.password}>
          <PasswordInput
            id="login-password"
            name="password"
            autoComplete="current-password"
            value={password}
            invalid={Boolean(fieldErrors.password)}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Checkbox
          checked={remember}
          onChange={setRemember}
          label="Keep me signed in on this device"
          hint="For 14 days of inactivity. Leave unticked on shared computers."
        />
        <Button type="submit" variant="primary" disabled={submitting} className="w-full justify-center">
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
      <p className="m-0 border-t border-bd pt-4 text-[11.5px] leading-normal text-tx3">
        There is no public registration. Forgotten your password? Ask an administrator to issue a
        new temporary password.
      </p>
    </AuthCard>
  );
}
