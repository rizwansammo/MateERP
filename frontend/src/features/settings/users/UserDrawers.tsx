'use client';

import { useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Choice';
import { Field } from '@/components/ui/Field';
import { Icon } from '@/components/ui/Icon';
import { Input, Select, Textarea } from '@/components/ui/Input';
import { Cell, DialogActions, DialogFooter, Drawer, FormGrid, Modal } from '@/components/ui/Overlay';
import { api } from '@/lib/api/client';
import type { Role, TemporaryPasswordResult, UserRecord } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDateTime } from '@/lib/format';
import { useFormState } from '@/lib/forms';

interface UserForm extends Record<string, unknown> {
  first_name: string;
  last_name: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
}

export function UserDrawer({ user, roles, onClose, onCreated, onSaved }: {
  user: UserRecord | null;
  roles: Role[];
  onClose: () => void;
  onCreated: (result: TemporaryPasswordResult) => void;
  onSaved: (user: UserRecord) => void;
}) {
  const { user: me } = useAuth();
  const isSelf = user?.id === me.id;
  const form = useFormState<UserForm>({
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
    username: user?.username ?? '',
    email: user?.email ?? '',
    role: user?.role ? String(user.role.id) : String(roles.find((r) => r.key === 'viewer')?.id ?? ''),
    is_active: user?.is_active ?? true,
  });
  const { values, set, errors } = form;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const local: Record<string, string> = {};
    if (!user && !/^[A-Za-z0-9._-]{3,150}$/.test(values.username)) local.username = 'Use 3–150 letters, digits, dots, hyphens or underscores.';
    if (!/^\S+@\S+\.\S+$/.test(values.email)) local.email = 'Enter a valid email address.';
    if (!values.role) local.role = 'Choose a role.';
    form.setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    setError(null);
    try {
      if (user) {
        const body: Record<string, unknown> = { first_name: values.first_name, last_name: values.last_name, email: values.email };
        if (!isSelf && Number(values.role) !== user.role?.id) body.role = Number(values.role);
        onSaved(await api.patch<UserRecord>(`/users/${user.id}/`, body));
      } else {
        onCreated(await api.post<TemporaryPasswordResult>('/users/', { ...values, role: Number(values.role) }));
      }
    } catch (err) {
      setError(form.applyError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer
      open
      onClose={onClose}
      width={560}
      eyebrow="Users & roles"
      title={user ? `Edit ${user.display_name}` : 'Create user'}
      description="Application access accounts only. Employee records belong in MateHR."
      footer={
        <DialogFooter>
          {!user && (
            <Banner tone="info" compact>
              MateERP generates a strong temporary password, shown once after creation. Share it securely; the user must
              change it at first sign-in. No email is sent.
            </Banner>
          )}
          {error && <Banner tone="err" compact>{error}</Banner>}
          <DialogActions>
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" onClick={() => void submit()} disabled={busy || (!!user && !form.dirty)}>
              {busy ? 'Saving…' : user ? 'Save changes' : 'Create user'}
            </Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      <FormGrid>
        <Cell w="half">
          <Field label="First name" htmlFor="u-first" error={errors.first_name}>
            <Input id="u-first" data-autofocus maxLength={150} value={values.first_name} onChange={(e) => set('first_name', e.target.value)} />
          </Field>
        </Cell>
        <Cell w="half">
          <Field label="Last name" htmlFor="u-last" error={errors.last_name}>
            <Input id="u-last" maxLength={150} value={values.last_name} onChange={(e) => set('last_name', e.target.value)} />
          </Field>
        </Cell>
        <Cell w="half">
          <Field label="Username" htmlFor="u-username" required error={errors.username} hint={user ? 'Usernames cannot be changed.' : undefined}>
            <Input id="u-username" autoComplete="off" disabled={Boolean(user)} maxLength={150} value={values.username} invalid={Boolean(errors.username)} onChange={(e) => set('username', e.target.value.trim())} />
          </Field>
        </Cell>
        <Cell w="half">
          <Field label="Email" htmlFor="u-email" required error={errors.email}>
            <Input id="u-email" type="email" maxLength={254} value={values.email} invalid={Boolean(errors.email)} onChange={(e) => set('email', e.target.value.trim())} />
          </Field>
        </Cell>
        <Cell>
          <Field label="Role" htmlFor="u-role" required error={errors.role} hint={isSelf ? 'You cannot change your own role.' : 'You can only assign roles whose permissions you hold.'}>
            <Select id="u-role" disabled={isSelf} value={values.role} invalid={Boolean(errors.role)} onChange={(e) => set('role', e.target.value)}>
              {roles.filter((r) => r.is_active || String(r.id) === values.role).map((r) => (
                <option key={r.id} value={r.id}>{r.name}{r.is_system ? '' : ' (custom)'}</option>
              ))}
            </Select>
          </Field>
        </Cell>
        {!user && (
          <Cell>
            <Checkbox checked={values.is_active} onChange={(v) => set('is_active', v)} label="Account active" hint="Inactive accounts cannot sign in." />
          </Cell>
        )}
      </FormGrid>
    </Drawer>
  );
}

/** Shows a generated temporary password exactly once. */
export function TemporaryPasswordDialog({ result, onClose }: { result: TemporaryPasswordResult | null; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  if (!result) return null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.temporary_password);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="One-time credential"
      title={`Temporary password for ${result.user.display_name}`}
      footer={
        <DialogFooter>
          <DialogActions>
            <Button variant="primary" onClick={onClose} data-autofocus>I have shared it securely</Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      <div className="flex flex-col gap-3 text-[13px] leading-[1.55] text-tx2">
        <p className="m-0">
          Give this password to <b className="text-tx">{result.user.username}</b> through a secure channel. It is shown
          only now — MateERP stores it encrypted and cannot display it again.
        </p>
        <div className="flex items-stretch border border-bd2">
          <code data-testid="temporary-password" className="flex-1 bg-sf2 px-3 py-2.5 font-mono text-[15px] font-semibold tracking-[.06em] text-tx select-all">
            {result.temporary_password}
          </code>
          <button type="button" onClick={() => void copy()} className="flex items-center gap-1 border-l border-bd2 bg-sf px-3 text-[12px] font-medium text-tx hover:bg-sf3">
            <Icon name={copied ? 'check' : 'content_copy'} size={16} />
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
        <p className="m-0 text-[12px] text-tx3">The user must choose a new password at first sign-in.</p>
      </div>
    </Modal>
  );
}

export function UserDetailDrawer({ user, onClose, actions }: { user: UserRecord; onClose: () => void; actions: React.ReactNode }) {
  const rows: [string, React.ReactNode][] = [
    ['Name', user.display_name],
    ['Username', <span key="u" className="font-mono text-[12px]">{user.username}</span>],
    ['Email', user.email],
    ['Role', user.role?.name ?? 'No role'],
    ['Status', <Badge key="s" tone={user.is_active ? 'ok' : 'neutral'}>{user.is_active ? 'Active' : 'Inactive'}</Badge>],
    ['Password', user.must_change_password ? 'Temporary — must change at next sign-in' : 'Set by user'],
    ['Last sign-in', formatDateTime(user.last_login)],
    ['Created', formatDateTime(user.date_joined)],
  ];
  return (
    <Drawer open onClose={onClose} width={520} eyebrow="User" title={user.display_name} description={user.email}
      footer={<DialogFooter><DialogActions>{actions}</DialogActions></DialogFooter>}>
      <dl className="m-0">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 border-b border-bd py-2 text-[12.5px]">
            <dt className="text-tx3">{label}</dt>
            <dd className="m-0 text-right text-tx">{value}</dd>
          </div>
        ))}
      </dl>
    </Drawer>
  );
}

interface RoleForm extends Record<string, unknown> {
  name: string;
  description: string;
  copyFrom: string;
}

export function RoleDrawer({ role, roles, onClose, onSaved }: {
  role: Role | null;
  roles: Role[];
  onClose: () => void;
  onSaved: (role: Role) => void;
}) {
  const { can } = useAuth();
  const form = useFormState<RoleForm>({ name: role?.name ?? '', description: role?.description ?? '', copyFrom: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (form.values.name.trim().length < 2) {
      form.setErrors({ name: 'Enter a role name.' });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (role) {
        const body: Record<string, unknown> = { description: form.values.description };
        if (!role.is_system) body.name = form.values.name.trim();
        onSaved(await api.patch<Role>(`/roles/${role.id}/`, body));
      } else {
        const source = roles.find((r) => String(r.id) === form.values.copyFrom);
        onSaved(await api.post<Role>('/roles/', {
          name: form.values.name.trim(),
          description: form.values.description,
          permissions: source ? source.permissions : [],
        }));
      }
    } catch (err) {
      setError(form.applyError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer
      open
      onClose={onClose}
      width={520}
      eyebrow="Roles"
      title={role ? `Edit ${role.name}` : 'New custom role'}
      description="Roles are application access profiles, not job titles. Assign permissions in Settings → Permissions."
      footer={
        <DialogFooter>
          {error && <Banner tone="err" compact>{error}</Banner>}
          <DialogActions>
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" onClick={() => void submit()} disabled={busy || !form.dirty}>{busy ? 'Saving…' : role ? 'Save role' : 'Create role'}</Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      <FormGrid>
        <Cell>
          <Field label="Role name" htmlFor="r-name" required error={form.errors.name} hint={role?.is_system ? 'Default roles keep their names.' : undefined}>
            <Input id="r-name" data-autofocus maxLength={80} disabled={role?.is_system} value={form.values.name} onChange={(e) => form.set('name', e.target.value)} />
          </Field>
        </Cell>
        <Cell>
          <Field label="Description" htmlFor="r-desc" error={form.errors.description}>
            <Textarea id="r-desc" rows={3} maxLength={300} value={form.values.description} onChange={(e) => form.set('description', e.target.value)} />
          </Field>
        </Cell>
        {!role && can('permissions.manage') && (
          <Cell>
            <Field label="Start with permissions from" htmlFor="r-copy" hint="Optional. You can only copy permissions you hold yourself.">
              <Select id="r-copy" value={form.values.copyFrom} onChange={(e) => form.set('copyFrom', e.target.value)}>
                <option value="">No permissions</option>
                {roles.filter((r) => !r.is_admin).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </Select>
            </Field>
          </Cell>
        )}
      </FormGrid>
    </Drawer>
  );
}
