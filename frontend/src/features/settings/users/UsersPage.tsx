'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Select } from '@/components/ui/Input';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel } from '@/components/ui/Panel';
import { FilterChips, Pager, SearchBox, SortHead, TableState, TableToolbar } from '@/components/ui/TableKit';
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import { invalidate, useQuery } from '@/lib/api/query';
import type { Page, Role, TemporaryPasswordResult, UserRecord } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';
import { useDebounced } from '@/lib/useDebounced';

import { Gate } from '../Gate';
import { RoleDrawer, TemporaryPasswordDialog, UserDetailDrawer, UserDrawer } from './UserDrawers';

export const ROLES_KEY = '/roles/';

export function useRoles() {
  return useQuery(ROLES_KEY, () => api.get<Role[]>('/roles/'));
}

type Status = 'all' | 'active' | 'inactive';
type SortKey = 'name' | 'role' | 'last_login' | 'date_joined';

export function UsersPage() {
  return (
    <Gate anyOf={['users.manage', 'roles.manage', 'permissions.manage']}>
      <UsersContent />
    </Gate>
  );
}

function UsersContent() {
  const { can } = useAuth();
  const roles = useRoles();
  const [creatingUser, setCreatingUser] = useState(false);
  const [roleDrawer, setRoleDrawer] = useState<Role | 'new' | null>(null);
  const [created, setCreated] = useState<TemporaryPasswordResult | null>(null);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Settings"
        title="Users & roles"
        description="Application users and their roles. These are access accounts only — employee records belong in MateHR."
        actions={
          <>
            {can('roles.manage') && <Button icon="shield" onClick={() => setRoleDrawer('new')}>New custom role</Button>}
            {can('users.manage') && <Button variant="primary" icon="person_add" onClick={() => setCreatingUser(true)}>Create user</Button>}
          </>
        }
      />
      {can('users.manage') && <UsersTable roles={roles.data ?? []} />}
      <RolesTable roles={roles.data} loading={roles.loading} error={roles.error} onEdit={(r) => setRoleDrawer(r)} />

      {creatingUser && roles.data && (
        <UserDrawer
          user={null}
          roles={roles.data}
          onClose={() => setCreatingUser(false)}
          onCreated={(result) => {
            setCreatingUser(false);
            setCreated(result);
            invalidate('/users/');
            invalidate(ROLES_KEY);
            toast(`User ${result.user.username} created`);
          }}
          onSaved={() => undefined}
        />
      )}
      <TemporaryPasswordDialog result={created} onClose={() => setCreated(null)} />
      {roleDrawer && roles.data && (
        <RoleDrawer
          role={roleDrawer === 'new' ? null : roleDrawer}
          roles={roles.data}
          onClose={() => setRoleDrawer(null)}
          onSaved={(role) => {
            setRoleDrawer(null);
            invalidate(ROLES_KEY);
            toast(roleDrawer === 'new' ? `Role ${role.name} created` : `Role ${role.name} saved`);
          }}
        />
      )}
    </PageContainer>
  );
}

function UsersTable({ roles }: { roles: Role[] }) {
  const { user: me } = useAuth();
  const [status, setStatus] = useState<Status>('all');
  const [role, setRole] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'name', dir: 'asc' });
  const [page, setPage] = useState(1);
  const q = useDebounced(search.trim());
  const pageSize = me.preferences.rows_per_page ?? 25;
  const params = { q, status: status === 'all' ? '' : status, role, ordering: `${sort.dir === 'desc' ? '-' : ''}${sort.key}`, page, page_size: pageSize };
  const key = `/users/?${new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString()}`;
  const users = useQuery(key, () => api.get<Page<UserRecord>>('/users/', params));

  const [editing, setEditing] = useState<UserRecord | null>(null);
  const [detail, setDetail] = useState<UserRecord | null>(null);
  const [confirm, setConfirm] = useState<{ kind: 'deactivate' | 'activate' | 'reset'; user: UserRecord } | null>(null);
  const [issued, setIssued] = useState<TemporaryPasswordResult | null>(null);

  const sortBy = (k: SortKey) => {
    setSort((s) => ({ key: k, dir: s.key === k && s.dir === 'asc' ? 'desc' : 'asc' }));
    setPage(1);
  };
  const refresh = () => {
    invalidate('/users/');
    invalidate(ROLES_KEY);
  };

  const rowActions = (u: UserRecord) => (
    <>
      <Button size="xs" onClick={() => setEditing(u)}>Edit</Button>
      {u.id !== me.id && (
        <Button size="xs" onClick={() => setConfirm({ kind: u.is_active ? 'deactivate' : 'activate', user: u })}>
          {u.is_active ? 'Deactivate' : 'Activate'}
        </Button>
      )}
      {u.id !== me.id && u.is_active && <Button size="xs" icon="key" onClick={() => setConfirm({ kind: 'reset', user: u })}>Reset password</Button>}
    </>
  );

  const data = users.data;
  return (
    <Panel>
      <TableToolbar title="Users" subtitle={data ? `${data.count} ${data.count === 1 ? 'user' : 'users'}` : undefined}>
        <FilterChips label="Status" value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={[{ value: 'all', label: 'All' }, { value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }]} />
        <span className="inline-block w-[170px]">
          <Select aria-label="Filter by role" value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }} controlSize="sm">
          <option value="">All roles</option>
          {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
        </span>
        <SearchBox value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Search name, username, email…" label="Search users" />
      </TableToolbar>
      <Table>
        <THead>
          <TR>
            <TH><SortHead label="User" active={sort.key === 'name'} dir={sort.dir} onSort={() => sortBy('name')} /></TH>
            <TH><SortHead label="Role" active={sort.key === 'role'} dir={sort.dir} onSort={() => sortBy('role')} /></TH>
            <TH>Status</TH>
            <TH><SortHead label="Last sign-in" active={sort.key === 'last_login'} dir={sort.dir} onSort={() => sortBy('last_login')} /></TH>
            <TH><SortHead label="Created" active={sort.key === 'date_joined'} dir={sort.dir} onSort={() => sortBy('date_joined')} /></TH>
            <TH align="right"><span className="sr-only">Actions</span></TH>
          </TR>
        </THead>
        <TBody>
          <TableState colSpan={6} loading={users.loading && !data} error={users.error ? errorMessage(users.error) : null} empty={data && data.count === 0 ? 'No users match these filters.' : null}>
            {data?.results.map((u) => (
              <TR key={u.id} className={u.is_active ? 'cursor-pointer' : 'cursor-pointer opacity-60'} onClick={() => setDetail(u)}>
                <TD>
                  <div className="min-w-0">
                    <div>{u.display_name}{u.id === me.id ? ' (you)' : ''}</div>
                    <div className="truncate text-[11.5px] text-tx3">{u.email} · <span className="font-mono">{u.username}</span></div>
                  </div>
                </TD>
                <TD>{u.role?.name ?? '—'}</TD>
                <TD>
                  <span className="flex flex-col items-start gap-1">
                    <Badge tone={u.is_active ? 'ok' : 'neutral'}>{u.is_active ? 'Active' : 'Inactive'}</Badge>
                    {u.must_change_password && u.is_active && <span className="text-[11px] text-warn">Temporary password</span>}
                  </span>
                </TD>
                <TD className="whitespace-nowrap text-tx2">{formatDate(u.last_login)}</TD>
                <TD className="whitespace-nowrap text-tx2">{formatDate(u.date_joined)}</TD>
                <TD align="right" onClick={(e) => e.stopPropagation()}>
                  <span className="inline-flex flex-nowrap justify-end gap-1">{rowActions(u)}</span>
                </TD>
              </TR>
            ))}
          </TableState>
        </TBody>
      </Table>
      {data && <Pager page={data.page} totalPages={data.total_pages} count={data.count} pageSize={data.page_size} onPage={setPage} />}

      {editing && (
        <UserDrawer
          user={editing}
          roles={roles}
          onClose={() => setEditing(null)}
          onCreated={() => undefined}
          onSaved={(u) => {
            setEditing(null);
            setDetail((d) => (d?.id === u.id ? u : d));
            refresh();
            toast(`${u.display_name} saved`);
          }}
        />
      )}
      {detail && <UserDetailDrawer user={detail} onClose={() => setDetail(null)} actions={rowActions(detail)} />}
      <ConfirmDialog
        open={confirm !== null}
        title={confirm?.kind === 'deactivate' ? `Deactivate ${confirm.user.display_name}?` : confirm?.kind === 'activate' ? `Activate ${confirm?.user.display_name}?` : `Reset password for ${confirm?.user.display_name}?`}
        confirmLabel={confirm?.kind === 'deactivate' ? 'Deactivate' : confirm?.kind === 'activate' ? 'Activate' : 'Issue temporary password'}
        danger={confirm?.kind === 'deactivate'}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (!confirm) return;
          const { kind, user } = confirm;
          if (kind === 'reset') {
            setIssued(await api.post<TemporaryPasswordResult>(`/users/${user.id}/reset-password/`));
          } else {
            const updated = await api.post<UserRecord>(`/users/${user.id}/${kind}/`);
            setDetail((d) => (d?.id === updated.id ? updated : d));
            toast(`${updated.display_name} ${kind === 'activate' ? 'activated' : 'deactivated'}`);
          }
          setConfirm(null);
          refresh();
        }}
      >
        {confirm?.kind === 'deactivate' && 'The user is signed out everywhere immediately and cannot sign in. Their history and audit attribution are kept. You can reactivate them later.'}
        {confirm?.kind === 'activate' && 'The user can sign in again with their existing password and role.'}
        {confirm?.kind === 'reset' && 'A new temporary password is generated and shown once. All of the user’s current sessions end and they must choose a new password at sign-in.'}
      </ConfirmDialog>
      <TemporaryPasswordDialog result={issued} onClose={() => setIssued(null)} />
    </Panel>
  );
}

function RolesTable({ roles, loading, error, onEdit }: { roles: Role[] | undefined; loading: boolean; error: unknown; onEdit: (role: Role) => void }) {
  const { can } = useAuth();
  const [confirm, setConfirm] = useState<Role | null>(null);
  const total = roles?.find((r) => r.is_admin)?.permissions.length ?? 0;
  return (
    <Panel>
      <TableToolbar title="Roles" subtitle="Default roles ship with MateERP; custom roles can be added. Administrator always holds every permission." />
      <Table>
        <THead>
          <TR>
            <TH>Role</TH>
            <TH>Description</TH>
            <TH align="right">Permissions</TH>
            <TH align="right">Active users</TH>
            <TH>Status</TH>
            <TH align="right"><span className="sr-only">Actions</span></TH>
          </TR>
        </THead>
        <TBody>
          <TableState colSpan={6} loading={loading && !roles} error={error ? errorMessage(error) : null}>
            {roles?.map((r) => (
              <TR key={r.id}>
                <TD>
                  <div className="font-medium">{r.name}</div>
                  <div className="text-[11.5px] text-tx3">{r.is_admin ? 'Locked default role' : r.is_system ? 'Default role' : 'Custom role'}</div>
                </TD>
                <TD className="text-tx2">{r.description || '—'}</TD>
                <TD align="right">{r.permissions.length} / {total}</TD>
                <TD align="right">{r.user_count}</TD>
                <TD><Badge tone={r.is_active ? 'ok' : 'neutral'}>{r.is_active ? 'Active' : 'Inactive'}</Badge></TD>
                <TD align="right">
                  <span className="inline-flex gap-1">
                    {can('permissions.manage') && (
                      <Link href={`/settings/permissions?role=${r.id}`} className="inline-flex h-[26px] items-center border border-bd2 bg-sf px-2 text-[11.5px] font-medium whitespace-nowrap text-tx hover:bg-sf3 hover:text-tx hover:no-underline">Permissions</Link>
                    )}
                    {can('roles.manage') && !r.is_admin && <Button size="xs" onClick={() => onEdit(r)}>Edit</Button>}
                    {can('roles.manage') && !r.is_admin && !r.is_system && (
                      <Button size="xs" onClick={() => setConfirm(r)}>{r.is_active ? 'Deactivate' : 'Activate'}</Button>
                    )}
                  </span>
                </TD>
              </TR>
            ))}
          </TableState>
        </TBody>
      </Table>
      <ConfirmDialog
        open={confirm !== null}
        title={`${confirm?.is_active ? 'Deactivate' : 'Activate'} role ${confirm?.name}?`}
        confirmLabel={confirm?.is_active ? 'Deactivate role' : 'Activate role'}
        danger={confirm?.is_active}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (!confirm) return;
          await api.patch<Role>(`/roles/${confirm.id}/`, { is_active: !confirm.is_active });
          invalidate(ROLES_KEY);
          toast(`Role ${confirm.name} ${confirm.is_active ? 'deactivated' : 'activated'}`);
          setConfirm(null);
        }}
      >
        {confirm?.is_active ? 'A role with active users cannot be deactivated — reassign them first.' : 'Users can be assigned this role again.'}
      </ConfirmDialog>
    </Panel>
  );
}
