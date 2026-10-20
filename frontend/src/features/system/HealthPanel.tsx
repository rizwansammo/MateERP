'use client';

import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Icon } from '@/components/ui/Icon';
import { Panel, PanelBody, PanelHeader } from '@/components/ui/Panel';
import { Spinner } from '@/components/ui/Spinner';
import { StatGrid } from '@/components/ui/StatGrid';
import { ApiError } from '@/lib/api/client';
import { type HealthReport, fetchHealth } from '@/lib/api/health';

type State =
  | { status: 'loading' }
  | { status: 'ready'; report: HealthReport }
  | { status: 'error'; error: Error };

/** Live backend status, fetched through the same-origin API proxy. */
export function HealthPanel() {
  const [state, setState] = useState<State>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal).then(
      (report) => setState({ status: 'ready', report }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: 'error', error: error instanceof Error ? error : new Error(String(error)) });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  const refresh = () => {
    setState({ status: 'loading' });
    setAttempt((n) => n + 1);
  };

  return (
    <Panel>
      <PanelHeader
        title="System status"
        subtitle="Backend API and database, checked live through the MateERP API."
        actions={
          <>
            {state.status === 'ready' && <StatusBadge report={state.report} />}
            {state.status === 'error' && <Badge tone="err">Unreachable</Badge>}
            <Button
              size="sm"
              icon="refresh"
              onClick={refresh}
              disabled={state.status === 'loading'}
            >
              Refresh
            </Button>
          </>
        }
      />
      {state.status === 'loading' && (
        <PanelBody className="flex items-center gap-2.5 text-[12.5px] text-tx3">
          <Spinner /> Checking backend…
        </PanelBody>
      )}
      {state.status === 'ready' && <HealthStats report={state.report} />}
      {state.status === 'error' && <HealthError error={state.error} />}
    </Panel>
  );
}

function StatusBadge({ report }: { report: HealthReport }) {
  return report.status === 'ok' ? (
    <Badge tone="ok">Operational</Badge>
  ) : (
    <Badge tone="warn">Degraded</Badge>
  );
}

function HealthStats({ report }: { report: HealthReport }) {
  const db = report.checks.database;
  const checkedAt = new Date(report.time);

  return (
    <div className="-m-px" data-testid="health-stats">
      <StatGrid
        stats={[
          {
            label: 'Backend API',
            icon: 'dns',
            value: report.status === 'ok' ? 'Operational' : 'Degraded',
            tone: report.status === 'ok' ? 'ok' : 'warn',
            sub: report.service,
          },
          {
            label: 'Database',
            icon: 'database',
            value: db.status === 'ok' ? 'Connected' : 'Unavailable',
            tone: db.status === 'ok' ? 'ok' : 'err',
            sub: db.latency_ms !== null ? `PostgreSQL · ${db.latency_ms} ms` : 'PostgreSQL',
          },
          { label: 'Version', icon: 'tag', value: report.version, sub: report.environment },
          {
            label: 'Server time',
            icon: 'schedule',
            value: checkedAt.toLocaleTimeString(),
            sub: checkedAt.toLocaleDateString(undefined, { dateStyle: 'medium' }),
          },
        ]}
      />
    </div>
  );
}

function HealthError({ error }: { error: Error }) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <PanelBody className="flex gap-3" >
      <Icon name="cloud_off" size={22} className="text-err" />
      <div role="alert" className="flex flex-col gap-1 text-[12.5px] leading-normal">
        <span className="font-semibold text-tx">The MateERP backend could not be reached.</span>
        <span className="text-tx2">{error.message}</span>
        <span className="text-tx3">
          Start the local stack with <code className="font-mono text-[12px]">docker compose up -d</code>{' '}
          and refresh.
          {requestId && <> Request ID: <code className="font-mono text-[12px]">{requestId}</code></>}
        </span>
      </div>
    </PanelBody>
  );
}
