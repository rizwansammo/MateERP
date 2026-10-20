import type { Metadata } from 'next';

import { Wordmark } from '@/components/brand/Wordmark';
import { Badge, type Tone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field } from '@/components/ui/Field';
import { AmountInput, Input, Select, Textarea } from '@/components/ui/Input';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader } from '@/components/ui/Panel';
import { Spinner } from '@/components/ui/Spinner';
import { StatGrid } from '@/components/ui/StatGrid';
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/Table';

export const metadata: Metadata = { title: 'Design System' };

/*
 * Internal reference for the MateERP design system (not in the main
 * navigation). Every value comes from tokens; sample content below is
 * illustrative typography only, not business data.
 */

const SWATCHES: Array<[string, string]> = [
  ['bg', 'Page background'],
  ['sf', 'Surface'],
  ['sf2', 'Surface 2'],
  ['sf3', 'Surface 3'],
  ['bd', 'Border'],
  ['bd2', 'Border strong'],
  ['tx', 'Text'],
  ['tx2', 'Text secondary'],
  ['tx3', 'Text muted'],
  ['ac', 'Accent (brand cyan)'],
  ['pr', 'Primary action'],
  ['lk', 'Link'],
  ['sb', 'Sidebar'],
  ['ok', 'Success'],
  ['warn', 'Warning'],
  ['err', 'Error'],
  ['info', 'Info'],
  ['neu', 'Neutral'],
];

const TONES: Tone[] = ['ok', 'warn', 'err', 'info', 'neutral', 'accent'];

export default function DesignSystemPage() {
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Internal reference"
        title="Design System"
        description="Tokens and components reproduced from the approved MateERP-UI prototype. Switch the theme in the header to review both palettes."
      />

      <Panel>
        <PanelHeader title="Wordmark" subtitle="Astro display face · M / ATE (0.667em) / ERP (cyan)" />
        <PanelBody className="flex flex-wrap items-center gap-10">
          <span className="text-[64px] text-tx">
            <Wordmark />
          </span>
          <span className="bg-sb px-[18px] py-4 text-[23px] text-splash-fg">
            <Wordmark />
          </span>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Colour tokens" subtitle="CSS variables in src/styles/tokens.css" />
        <div className="grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-px bg-bd">
          {SWATCHES.map(([token, name]) => (
            <div key={token} className="flex items-center gap-3 bg-sf p-3">
              <span className="size-8 flex-none border border-bd" style={{ background: `var(--${token})` }} />
              <span className="flex min-w-0 flex-col">
                <span className="text-[12.5px] font-medium text-tx">{name}</span>
                <span className="font-mono text-[11px] text-tx3">--{token}</span>
              </span>
            </div>
          ))}
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Typography" subtitle="IBM Plex Sans · IBM Plex Mono for references and figures" />
        <PanelBody className="flex flex-col gap-3">
          <div className="text-[24px] font-semibold tracking-[-.015em]">Page title · 24 / 600</div>
          <div className="text-[19px] font-semibold tracking-[-.01em]">Drawer title · 19 / 600</div>
          <div className="text-[13.5px] font-semibold">Panel title · 13.5 / 600</div>
          <div className="text-[13px] text-tx2">Body text · 13 / 400</div>
          <div className="text-[10.5px] font-semibold uppercase tracking-[.08em] text-tx3">Label · 10.5 / 600 uppercase</div>
          <div className="font-mono text-[12px] text-tx2">INV-0001 · 1,250.00 · mono 12</div>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Buttons and badges" />
        <PanelBody className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" icon="add">Primary</Button>
            <Button variant="secondary" icon="download">Secondary</Button>
            <Button variant="danger" icon="delete">Danger</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="primary" disabled>Disabled</Button>
            <Button size="sm" icon="filter_list">Small</Button>
            <Spinner />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {TONES.map((tone) => (
              <Badge key={tone} tone={tone}>{tone}</Badge>
            ))}
          </div>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Form controls" />
        <PanelBody className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="Text input" htmlFor="ds-text" required hint="Helper text">
            <Input id="ds-text" placeholder="Placeholder" />
          </Field>
          <Field label="Amount" htmlFor="ds-amount" hint="Amounts are kept as exact decimal strings.">
            <AmountInput id="ds-amount" placeholder="0.00" />
          </Field>
          <Field label="Select" htmlFor="ds-select">
            <Select id="ds-select" defaultValue="a">
              <option value="a">Option A</option>
              <option value="b">Option B</option>
            </Select>
          </Field>
          <Field label="Invalid input" htmlFor="ds-invalid" error="This field is required.">
            <Input id="ds-invalid" invalid aria-describedby="ds-invalid-error" />
          </Field>
          <div className="md:col-span-2">
            <Field label="Textarea" htmlFor="ds-notes">
              <Textarea id="ds-notes" rows={3} />
            </Field>
          </div>
        </PanelBody>
      </Panel>

      <StatGrid
        stats={[
          { label: 'Stat tile', value: '1,250.00', sub: 'Default tone', icon: 'payments' },
          { label: 'Positive', value: 'Ready', sub: 'ok tone', tone: 'ok' },
          { label: 'Attention', value: '3 items', sub: 'warn tone', tone: 'warn' },
          { label: 'Accent', value: 'Live', sub: 'accent tone', tone: 'accent' },
        ]}
      />

      <Panel>
        <PanelHeader title="Table" subtitle="Monetary columns are right-aligned with tabular figures" />
        <Table>
          <THead>
            <TR>
              <TH>Reference</TH>
              <TH>Description</TH>
              <TH>Status</TH>
              <TH align="right">Amount</TH>
            </TR>
          </THead>
          <TBody>
            <TR>
              <TD className="font-mono text-[12px]">REF-0001</TD>
              <TD>Sample row</TD>
              <TD><Badge tone="ok">Posted</Badge></TD>
              <TD align="right" className="font-medium">1,250.00</TD>
            </TR>
            <TR>
              <TD className="font-mono text-[12px]">REF-0002</TD>
              <TD>Sample row</TD>
              <TD><Badge tone="warn">Pending</Badge></TD>
              <TD align="right" className="font-medium">98.40</TD>
            </TR>
          </TBody>
        </Table>
        <EmptyState icon="inbox" title="Empty state">
          Shown when a list has no records yet.
        </EmptyState>
      </Panel>
    </PageContainer>
  );
}
