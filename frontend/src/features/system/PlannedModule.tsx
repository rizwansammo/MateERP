import { Badge } from '@/components/ui/Badge';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader } from '@/components/ui/Panel';
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { type NavItem, type NavSub, PHASES, CURRENT_PHASE } from '@/lib/navigation';

/*
 * Honest placeholder for modules that a later phase delivers. It states the
 * planned scope and phase and offers no actions or sample data.
 */

export function PlannedNotice({ item }: { item: NavItem }) {
  return (
    <Panel>
      <PanelHeader
        title={`${item.label} — planned`}
        subtitle={`Phase ${item.phase} · ${PHASES[item.phase]}`}
        actions={<Badge tone="neutral">Not yet available</Badge>}
      />
      <PanelBody className="text-[13px] leading-[1.55] text-tx2">
        {item.summary} This module is not implemented yet, so no figures are shown.
      </PanelBody>
    </Panel>
  );
}

interface PlannedModuleProps {
  item: NavItem;
  group: string;
  current: NavSub | null;
}

export function PlannedModule({ item, group, current }: PlannedModuleProps) {
  const phase = current?.phase ?? item.phase;
  const scope = current?.phase ? current.label : item.label;
  const sections = item.subs?.filter(s => (s.phase ?? item.phase) > CURRENT_PHASE);
  return (
    <PageContainer>
      <PageHeader
        eyebrow={group}
        title={current && current.slug !== item.subs?.[0]?.slug ? current.label : item.label}
        description={current?.phase ? `${scope} will be delivered in ${PHASES[phase]}.` : item.summary}
        actions={<Badge tone="info">{`Planned · Phase ${phase}`}</Badge>}
      />

      <Panel>
        <PanelHeader
          title="Delivery status"
          subtitle={`Phase ${phase} · ${PHASES[phase]}`}
        />
        <PanelBody className="text-[13px] leading-[1.55] text-tx2">
          <p className="m-0" data-testid="planned-notice">
            <strong className="font-semibold text-tx">{scope}</strong> is scheduled for Phase{' '}
            {phase} of the MateERP roadmap and is not implemented yet. No records are shown
            and no actions are available until it is delivered.
          </p>
        </PanelBody>
      </Panel>

      {Boolean(sections?.length) && (
        <Panel>
          <PanelHeader title="Planned sections" subtitle={`${sections?.length} sections`} />
          <Table>
            <THead>
              <TR>
                <TH>Section</TH>
                <TH>Route</TH>
                <TH align="right">Status</TH>
              </TR>
            </THead>
            <TBody>
              {sections?.map((s) => (
                <TR key={s.slug} aria-current={current?.slug === s.slug ? 'page' : undefined}>
                  <TD className={current?.slug === s.slug ? 'font-semibold' : undefined}>
                    {s.label}
                  </TD>
                  <TD className="font-mono text-[12px] text-tx3">{`/${item.id}/${s.slug}`}</TD>
                  <TD align="right">
                    <Badge tone="neutral">Planned</Badge>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Panel>
      )}
    </PageContainer>
  );
}
