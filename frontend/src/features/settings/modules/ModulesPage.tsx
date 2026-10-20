'use client';

import { useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Banner } from '@/components/ui/Banner';
import { ToggleButton } from '@/components/ui/Choice';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel } from '@/components/ui/Panel';
import { TableState } from '@/components/ui/TableKit';
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import { MODULES_KEY, useModules } from '@/lib/api/hooks';
import { invalidate } from '@/lib/api/query';
import type { ModuleInfo } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';

export function ModulesPage() {
  const { can } = useAuth();
  const modules = useModules();
  const [busy, setBusy] = useState<string | null>(null);
  const editable = can('company.edit');

  const toggle = async (m: ModuleInfo) => {
    setBusy(m.key);
    try {
      await api.put(`/modules/${m.key}/`, { enabled: !m.enabled });
      invalidate(MODULES_KEY);
      toast(`${m.label} ${m.enabled ? 'hidden' : 'enabled'}`);
    } catch (err) {
      toast(errorMessage(err), 'err');
    } finally {
      setBusy(null);
    }
  };

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Settings"
        title="Modules"
        description="Enable or hide optional modules. Core accounting, financial integrity, permissions and audit always stay on. Hiding a module never deletes its records."
      />
      <Banner tone="info">
        Enabling a module makes it visible; it does not make an unfinished module work. Modules that are not built yet stay marked “Planned” with the phase that delivers them.
      </Banner>
      <Panel>
        <Table>
          <THead>
            <TR>
              <TH>Module</TH>
              <TH>Delivery</TH>
              <TH>Status</TH>
              <TH align="right"><span className="sr-only">Toggle</span></TH>
            </TR>
          </THead>
          <TBody>
            <TableState colSpan={4} loading={modules.loading && !modules.data} error={modules.error ? errorMessage(modules.error) : null}>
              {modules.data?.optional.map((m) => (
                <TR key={m.key}>
                  <TD>
                    <div className="font-medium">{m.label}</div>
                    <div className="text-[11.5px] text-tx3">{m.description}</div>
                  </TD>
                  <TD>{m.implemented ? <Badge tone="ok">Functional</Badge> : <Badge tone="neutral">{`Planned · Phase ${m.phase}`}</Badge>}</TD>
                  <TD><Badge tone={m.enabled ? 'ok' : 'neutral'}>{m.enabled ? 'Enabled' : 'Hidden'}</Badge></TD>
                  <TD align="right">
                    <ToggleButton on={m.enabled} label={`${m.label} module`} disabled={!editable || busy === m.key} onToggle={() => void toggle(m)} />
                  </TD>
                </TR>
              ))}
              {modules.data?.core.map((name) => (
                <TR key={name}>
                  <TD>
                    <div className="font-medium">{name}</div>
                    <div className="text-[11.5px] text-tx3">Always on</div>
                  </TD>
                  <TD><span className="text-tx3">—</span></TD>
                  <TD><Badge tone="info">Core</Badge></TD>
                  <TD align="right"><span className="text-[12px] text-tx3">Mandatory</span></TD>
                </TR>
              ))}
            </TableState>
          </TBody>
        </Table>
      </Panel>
    </PageContainer>
  );
}
