'use client';

import { useSearchParams } from 'next/navigation';
import { Fragment, useMemo, useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel } from '@/components/ui/Panel';
import { Spinner } from '@/components/ui/Spinner';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import { invalidate, useQuery } from '@/lib/api/query';
import type { PermissionDef, Role } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { cn } from '@/lib/cn';

import { Gate } from '../Gate';
import { ROLES_KEY, useRoles } from '../users/UsersPage';

export function PermissionsPage() {
  return (
    <Gate anyOf={['permissions.manage', 'roles.manage']}>
      <MatrixContent />
    </Gate>
  );
}

type Pending = Record<number, Set<string>>;

export function diffCount(roles: Role[], pending: Pending): number {
  let n = 0;
  for (const role of roles) {
    const next = pending[role.id];
    if (!next) continue;
    const before = new Set(role.permissions);
    for (const code of next) if (!before.has(code)) n++;
    for (const code of before) if (!next.has(code)) n++;
  }
  return n;
}

function MatrixContent() {
  const { can, user, refresh: refreshMe } = useAuth();
  const roles = useRoles();
  const catalog = useQuery('/permissions/', () => api.get<PermissionDef[]>('/permissions/'));
  const focusRole = Number(useSearchParams().get('role')) || null;
  const [pending, setPending] = useState<Pending>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editable = can('permissions.manage');

  const columns = useMemo(() => (roles.data ?? []).filter((r) => r.is_active), [roles.data]);
  const groups = useMemo(() => {
    const out = new Map<string, PermissionDef[]>();
    for (const p of catalog.data ?? []) out.set(p.category_label, [...(out.get(p.category_label) ?? []), p]);
    return [...out.entries()];
  }, [catalog.data]);
  const changes = diffCount(columns, pending);

  const granted = (role: Role, code: string) => (pending[role.id] ?? new Set(role.permissions)).has(code);
  const changed = (role: Role, code: string) => pending[role.id] !== undefined && pending[role.id]!.has(code) !== role.permissions.includes(code);

  const toggle = (role: Role, code: string) => {
    setPending((p) => {
      const next = new Set(p[role.id] ?? role.permissions);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return { ...p, [role.id]: next };
    });
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    const touched = columns.filter((r) => pending[r.id]);
    try {
      const body = Object.fromEntries(touched.map((r) => [String(r.id), [...pending[r.id]!]]));
      roles.mutate(await api.post<Role[]>('/roles/permissions/', { changes: body }));
      setPending({});
      invalidate(ROLES_KEY);
      void refreshMe();
      toast(`Permissions saved for ${touched.map((r) => r.name).join(', ')}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  if (!roles.data || !catalog.data) {
    return <PageContainer><div className="flex items-center gap-2 text-[12.5px] text-tx3"><Spinner /> Loading permissions…</div></PageContainer>;
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Settings"
        title="Permissions"
        description="Select cells to grant or revoke permissions, then save. Changes apply to signed-in users on their next request — permissions are evaluated on the server every time."
      />
      <Banner tone="info">
        Signed in as {user.display_name} ({user.role?.name ?? 'no role'}). Administrator keeps full access by design. You can only grant or revoke
        permissions you hold yourself.{!editable && ' You can view this matrix but not change it.'}
      </Banner>
      {error && <Banner tone="err">{error}</Banner>}

      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] border-collapse text-[13px]">
            <thead className="sticky top-0 z-[1] bg-sf2">
              <tr className="border-b border-bd">
                <th scope="col" className="px-3 py-[9px] text-left text-[10.5px] font-semibold uppercase tracking-[.07em] text-tx3">Permission</th>
                {columns.map((r) => (
                  <th key={r.id} scope="col" className={cn('w-[140px] px-2 py-[9px] text-center text-[10.5px] font-semibold uppercase tracking-[.07em]', r.id === focusRole ? 'bg-infos text-tx' : 'text-tx3')}>
                    {r.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map(([category, perms]) => (
                <Fragment key={category}>
                  <tr className="border-b border-bd bg-sf3">
                    <th scope="colgroup" colSpan={columns.length + 1} className="px-3 py-1.5 text-left text-[10.5px] font-semibold uppercase tracking-[.1em] text-tx2">{category}</th>
                  </tr>
                  {perms.map((p) => (
                    <tr key={p.code} className="border-b border-bd hover:bg-sfh">
                      <th scope="row" className="px-3 py-2 text-left font-normal">
                        <div className="text-tx">{p.label}</div>
                        <div className="font-mono text-[11px] text-tx3">{p.code}</div>
                      </th>
                      {columns.map((r) => {
                        const on = granted(r, p.code);
                        const locked = r.is_admin || !editable;
                        return (
                          <td key={r.id} className={cn('px-2 py-1.5 text-center', changed(r, p.code) && 'bg-infos', r.id === focusRole && !changed(r, p.code) && 'bg-infos/40')}>
                            <button
                              type="button"
                              role="switch"
                              aria-checked={on}
                              aria-label={`${p.label} for ${r.name}`}
                              disabled={locked}
                              onClick={() => toggle(r, p.code)}
                              className={cn(
                                'h-7 w-full max-w-[118px] border text-[11.5px] font-semibold',
                                on ? 'border-transparent bg-oks text-ok' : 'border-transparent bg-transparent font-normal text-tx3',
                                !locked && 'hover:border-bd2',
                                locked && 'cursor-default',
                              )}
                            >
                              {on ? '✓ Granted' : '— Denied'}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {changes > 0 && (
        <div role="region" aria-label="Unsaved permission changes" className="sticky bottom-4 z-10 flex flex-wrap items-center justify-between gap-3 border border-bd2 bg-sf px-4 py-3 shadow-[0_18px_50px_rgba(0,0,0,.18)]">
          <span className="text-[12.5px] text-tx">
            <b>{changes}</b> unsaved {changes === 1 ? 'change' : 'changes'} in {columns.filter((r) => pending[r.id]).map((r) => r.name).join(', ')}
          </span>
          <span className="flex gap-2">
            <Button onClick={() => setPending({})} disabled={saving}>Discard</Button>
            <Button variant="primary" onClick={() => void save()} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</Button>
          </span>
        </div>
      )}
    </PageContainer>
  );
}
