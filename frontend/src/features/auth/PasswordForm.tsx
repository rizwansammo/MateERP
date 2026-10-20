'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { type FormEvent, useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { ApiError, api } from '@/lib/api/client';

import { AuthCard } from './AuthLayout';
import { PasswordInput } from './PasswordInput';

type Fields = 'current_password' | 'new_password' | 'confirm';

export function validateNewPassword(next: string, confirm: string): Partial<Record<Fields, string>> {
  const errors: Partial<Record<Fields, string>> = {};
  if (next.length < 12) errors.new_password = 'Use at least 12 characters.';
  else if (/^\d+$/.test(next)) errors.new_password = 'The password cannot be entirely numeric.';
  if (confirm !== next) errors.confirm = 'The passwords do not match.';
  return errors;
}

export function PasswordForm({ forced, displayName }: { forced: boolean; displayName: string }) {
  const router = useRouter();
  const [values, setValues] = useState({ current_password: '', new_password: '', confirm: '' });
  const [errors, setErrors] = useState<Partial<Record<Fields, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const set = (key: Fields) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    const local = validateNewPassword(values.new_password, values.confirm);
    if (!values.current_password) local.current_password = 'Enter your current password.';
    setErrors(local);
    if (Object.keys(local).length) return;

    setSubmitting(true);
    setError(null);
    try {
      await api.post('/auth/password/', {
        current_password: values.current_password,
        new_password: values.new_password,
      });
      router.replace('/dashboard?password=changed');
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.code === 'validation_error') setErrors(err.fieldErrors());
      else setError(err instanceof Error ? err.message : 'The password could not be changed.');
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      eyebrow={forced ? 'Action required' : 'Account security'}
      title={forced ? 'Set your password' : 'Change password'}
      description={
        forced
          ? `Welcome, ${displayName}. You signed in with a temporary password — choose your own to continue.`
          : 'Other signed-in devices will be signed out after the change.'
      }
    >
      {error && <Banner tone="err" compact>{error}</Banner>}
      <form noValidate onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label={forced ? 'Temporary password' : 'Current password'} htmlFor="pw-current" error={errors.current_password}>
          <PasswordInput id="pw-current" autoComplete="current-password" autoFocus value={values.current_password}
            invalid={Boolean(errors.current_password)} onChange={set('current_password')} />
        </Field>
        <Field label="New password" htmlFor="pw-new" error={errors.new_password}
          hint="At least 12 characters. Avoid common words and your name.">
          <PasswordInput id="pw-new" autoComplete="new-password" value={values.new_password}
            invalid={Boolean(errors.new_password)} onChange={set('new_password')} />
        </Field>
        <Field label="Confirm new password" htmlFor="pw-confirm" error={errors.confirm}>
          <PasswordInput id="pw-confirm" autoComplete="new-password" value={values.confirm}
            invalid={Boolean(errors.confirm)} onChange={set('confirm')} />
        </Field>
        <Button type="submit" variant="primary" disabled={submitting} className="w-full justify-center">
          {submitting ? 'Saving…' : 'Save new password'}
        </Button>
      </form>
      <div className="flex justify-between border-t border-bd pt-4 text-[12px]">
        {forced ? <span className="text-tx3">Signed in as {displayName}</span> : <Link href="/dashboard">Back to MateERP</Link>}
        <SignOutLink />
      </div>
    </AuthCard>
  );
}

function SignOutLink() {
  const router = useRouter();
  return (
    <button
      type="button"
      className="bg-transparent text-[12px] font-medium text-lk hover:text-ac"
      onClick={async () => {
        await api.post('/auth/logout/').catch(() => undefined);
        router.replace('/login');
        router.refresh();
      }}
    >
      Sign out
    </button>
  );
}
