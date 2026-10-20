'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { InfoPanel, InfoPanels } from '@/components/ui/InfoPanel';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel } from '@/components/ui/Panel';
import { Spinner } from '@/components/ui/Spinner';
import { StatGrid } from '@/components/ui/StatGrid';
import { TableToolbar } from '@/components/ui/TableKit';
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import { useQuery } from '@/lib/api/query';
import type { BrandingOverview, BrandingVersionDetail, BusinessSettings } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDateTime, titleCase } from '@/lib/format';

import { Gate } from '../Gate';
import { NumberingDrawer } from '../NumberingDrawer';
import { BrandingStudio } from './BrandingStudio';
import { PublishDialog } from './PublishDialog';
import { VersionViewer } from './VersionViewer';

export const BRANDING_KEY = '/branding/';

export function BrandingPage() {
  return (
    <Gate anyOf={['branding.manage', 'company.view']}>
      <BrandingContent />
    </Gate>
  );
}

const SEAL_LABEL = { editor: 'Stamp', image: 'Image', none: 'None' } as const;

function BrandingContent() {
  const { can } = useAuth();
  const query = useQuery(BRANDING_KEY, () => api.get<BrandingOverview>('/branding/'));
  const [studio, setStudio] = useState<null | 'invoice' | 'receipt'>(null);
  const [viewing, setViewing] = useState<{ version: BrandingVersionDetail; doc: 'invoice' | 'receipt' } | null>(null);
  const [restore, setRestore] = useState<number | null>(null);
  const [numbering, setNumbering] = useState<Record<string, string> | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const manage = can('branding.manage');
  const data = query.data;

  if (query.loading && !data) {
    return <PageContainer><div className="flex items-center gap-2 text-[12.5px] text-tx3"><Spinner /> Loading branding…</div></PageContainer>;
  }
  if (!data) return <PageContainer><Banner tone="err">{errorMessage(query.error)}</Banner></PageContainer>;

  const current = data.current;
  const cfg = current?.config ?? data.draft.config;
  const companyName = data.company?.legal_name || data.company?.display_name || 'your company';
  const preview = async (doc: 'invoice' | 'receipt') => {
    if (current) setViewing({ version: current, doc });
  };
  const openVersion = async (number: number) => {
    try {
      setViewing({ version: await api.get<BrandingVersionDetail>(`/branding/versions/${number}/`), doc: 'invoice' });
    } catch (err) {
      toast(errorMessage(err), 'err');
    }
  };
  const openNumbering = async () => {
    try {
      setNumbering((await api.get<BusinessSettings>('/settings/business/')).numbering);
    } catch (err) {
      toast(errorMessage(err), 'err');
    }
  };

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Settings"
        title="Invoice & receipt branding"
        description={`Templates, colours, logo, signature, seal and numbering for ${companyName}. Every publish creates a version; issued documents keep the version they were issued with.`}
        actions={
          <>
            <Button icon="receipt" onClick={() => void preview('receipt')} disabled={!current}>Preview receipt</Button>
            <Button icon="visibility" onClick={() => void preview('invoice')} disabled={!current}>Preview invoice</Button>
            {manage && <Button variant="primary" icon="palette" onClick={() => setStudio('invoice')}>Open branding editor</Button>}
          </>
        }
      />

      <StatGrid
        small
        stats={[
          { label: 'Current version', value: current ? current.label || `Version ${current.number}` : 'Not published', sub: current ? `Published ${formatDateTime(current.published_at)}` : 'Publish to apply to documents', accentBar: true },
          { label: 'Invoice template', value: titleCase(cfg.invoice_template), sub: `${cfg.header_layout} · ${cfg.typography} · ${cfg.table_style}`, accentBar: true },
          { label: 'Receipt template', value: cfg.receipt_template === 'official' ? 'Official' : 'Compact', sub: `Seal: ${SEAL_LABEL[cfg.seal.mode]}`, accentBar: true },
          { label: 'Next numbers', value: data.numbering.next_invoice, sub: data.numbering.next_receipt, accentBar: true },
        ]}
      />

      {data.pending_request && (
        <Banner tone="warn" action={<Link href="/settings/approvals" className="text-[12.5px] font-medium">Review</Link>}>
          “{data.pending_request.title}” was submitted by {data.pending_request.requested_by.display_name} and is waiting for approval. It is not published yet.
        </Banner>
      )}
      {data.has_unpublished_changes && current && manage && (
        <Banner
          tone="info"
          action={
            <span className="flex gap-3 text-[12.5px] font-medium">
              <button type="button" className="bg-transparent text-lk hover:text-ac" onClick={() => setStudio('invoice')}>Open editor</button>
              <button type="button" className="bg-transparent text-lk hover:text-ac" onClick={() => setConfirmDiscard(true)}>Discard draft</button>
            </span>
          }
        >
          The draft has unpublished changes{data.draft.updated_by ? ` (last saved by ${data.draft.updated_by}, ${formatDateTime(data.draft.updated_at)})` : ''}. Documents keep using version {current.number} until you publish.
        </Banner>
      )}
      {!data.company && (
        <Banner tone="warn" action={<Link href="/settings/company" className="text-[12.5px] font-medium">Set up company</Link>}>
          The company profile is not set up yet. Branding can be drafted, but publishing needs the company name and address.
        </Banner>
      )}
      {current && (
        <Banner tone="info">
          Historical preservation: invoices and receipts issued from Phase 4 onward record the branding version they were issued with and always render with it.
        </Banner>
      )}

      <InfoPanels>
        <InfoPanel
          title="Invoice design"
          rows={[
            { label: 'Template', value: titleCase(cfg.invoice_template) },
            { label: 'Brand / accent', value: `${cfg.brand_color} / ${cfg.accent_color}` },
            { label: 'Header layout', value: cfg.header_layout },
            { label: 'Typography', value: cfg.typography },
            { label: 'Spacing & table', value: `${cfg.spacing} · ${cfg.table_style}` },
            ...(manage ? [{ label: 'Edit', value: 'Template, colours & text →', onClick: () => setStudio('invoice') }] : []),
          ]}
        />
        <InfoPanel
          title="Identity assets"
          rows={[
            { label: 'Company logo', value: data.company?.logo_url ? `Uploaded (${cfg.logo_size}px)` : 'Not uploaded — initials used' },
            { label: 'Authorised signature', value: cfg.signature_name ? `${current?.signature_url || data.draft.signature_url ? 'Image' : 'Typed'} · ${cfg.signature_name}` : 'Not set' },
            { label: 'Company seal', value: cfg.seal.mode === 'editor' ? `${titleCase(cfg.seal.shape)} stamp · ${cfg.seal.center}` : SEAL_LABEL[cfg.seal.mode] },
            { label: 'Custom fields', value: cfg.custom_fields.map((f) => f.label).join(', ') },
          ]}
        />
        <InfoPanel
          title="Receipts & numbering"
          rows={[
            { label: 'Receipt template', value: cfg.receipt_template === 'official' ? 'Official (framed)' : 'Compact' },
            { label: 'Logo on receipts', value: cfg.show_logo_on_receipt ? 'Shown' : 'Hidden' },
            { label: 'Invoice format', value: data.numbering.invoice },
            { label: 'Receipt format', value: data.numbering.receipt },
            ...(can('company.edit') ? [{ label: 'Numbering', value: 'Edit formats →', onClick: () => void openNumbering() }] : []),
          ]}
        />
      </InfoPanels>

      <Panel>
        <TableToolbar title="Branding versions" subtitle="Published versions are immutable. Restoring creates a new version." />
        {data.versions.length === 0 ? (
          <EmptyState icon="history" title="Not published yet">
            {manage ? 'Open the branding editor, preview the documents and publish the first version.' : 'No branding has been published.'}
          </EmptyState>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Version</TH>
                <TH>Template</TH>
                <TH>Colours</TH>
                <TH>Published</TH>
                <TH>Status</TH>
                <TH align="right"><span className="sr-only">Actions</span></TH>
              </TR>
            </THead>
            <TBody>
              {data.versions.map((v) => {
                const isCurrent = v.number === current?.number;
                return (
                  <TR key={v.number}>
                    <TD>
                      <div className="font-medium">{v.label || `Version ${v.number}`}</div>
                      <div className="text-[11.5px] text-tx3">
                        Version {v.number}{v.restored_from ? ` · restored from ${v.restored_from}` : ''}{v.approved ? ' · approved' : ''}
                      </div>
                    </TD>
                    <TD>{titleCase(v.invoice_template)}</TD>
                    <TD className="font-mono text-[12px]">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="size-3 border border-bd2" style={{ background: v.brand_color }} />
                        <span className="size-3 border border-bd2" style={{ background: v.accent_color }} />
                        {v.brand_color} / {v.accent_color}
                      </span>
                    </TD>
                    <TD>
                      <div>{v.published_by}</div>
                      <div className="text-[11.5px] text-tx3">{formatDateTime(v.published_at)}</div>
                    </TD>
                    <TD><Badge tone={isCurrent ? 'ok' : 'neutral'}>{isCurrent ? 'Current' : 'Historical'}</Badge></TD>
                    <TD align="right">
                      <span className="inline-flex gap-1">
                        <Button size="xs" icon="visibility" onClick={() => void openVersion(v.number)}>Preview</Button>
                        {manage && !isCurrent && (
                          <Button size="xs" icon="restore" onClick={() => setRestore(v.number)} disabled={Boolean(data.pending_request)}>Restore</Button>
                        )}
                      </span>
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        )}
      </Panel>

      {studio && (
        <BrandingStudio overview={data} initialDoc={studio} onChange={(next) => query.mutate(next)} onClose={() => setStudio(null)} />
      )}
      {viewing && (
        <VersionViewer version={viewing.version} initialDoc={viewing.doc} display={data.display} onClose={() => setViewing(null)} />
      )}
      <PublishDialog
        open={restore !== null}
        restoreVersion={restore ?? undefined}
        approvalRequired={data.approval_required}
        onCancel={() => setRestore(null)}
        onDone={(result, next) => {
          setRestore(null);
          query.mutate(next);
          toast(result.status === 'published' ? `Restored as version ${result.version.number}` : 'Restore submitted for approval');
        }}
      />
      <ConfirmDialog
        open={confirmDiscard}
        title="Discard the branding draft?"
        confirmLabel="Discard draft"
        danger
        onCancel={() => setConfirmDiscard(false)}
        onConfirm={async () => {
          query.mutate(await api.post<BrandingOverview>('/branding/draft/discard/'));
          setConfirmDiscard(false);
          toast('Draft reset to the published version');
        }}
      >
        The draft returns to the current published version. Uploaded files stay in history.
      </ConfirmDialog>
      {numbering && (
        <NumberingDrawer
          numbering={numbering}
          onClose={() => setNumbering(null)}
          onSaved={() => {
            setNumbering(null);
            void query.refresh();
            toast('Number formats saved');
          }}
        />
      )}
    </PageContainer>
  );
}
