'use client';

import { useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { FileDrop, checkImage } from '@/components/ui/FileDrop';
import { InfoPanel, InfoPanels } from '@/components/ui/InfoPanel';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader } from '@/components/ui/Panel';
import { Spinner } from '@/components/ui/Spinner';
import { toast } from '@/components/ui/Toast';
import { ApiError, api, errorMessage } from '@/lib/api/client';
import { COMPANY_SUMMARY_KEY, useCurrencies } from '@/lib/api/hooks';
import { invalidate, useQuery } from '@/lib/api/query';
import type { CompanyProfile } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { MONTHS, formatDateTime } from '@/lib/format';

import { Gate } from '../Gate';
import { CompanyDrawer } from './CompanyDrawer';

export const COMPANY_KEY = '/company/';

function useCompany() {
  return useQuery(COMPANY_KEY, async () => {
    try {
      return await api.get<CompanyProfile>('/company/');
    } catch (error) {
      if (error instanceof ApiError && error.code === 'company_not_configured') return null;
      throw error;
    }
  });
}

export function CompanyPage() {
  return (
    <Gate anyOf={['company.view', 'company.edit', 'branding.manage']}>
      <CompanyContent />
    </Gate>
  );
}

function CompanyContent() {
  const { can } = useAuth();
  const company = useCompany();
  const currencies = useCurrencies();
  const [editing, setEditing] = useState(false);
  const canEdit = can('company.edit');
  const data = company.data;

  const currencyName = (code: string) => {
    const c = currencies.data?.find((x) => x.code === code);
    return c ? `${c.code} — ${c.name}` : code;
  };

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Settings"
        title="Company profile"
        description="This installation belongs to exactly one company. Its identity appears on invoices and receipts; MateERP’s own product branding is separate."
        actions={
          data && canEdit ? (
            <Button variant="primary" icon="edit" onClick={() => setEditing(true)}>
              Edit company profile
            </Button>
          ) : null
        }
      />

      {company.loading && !data && (
        <Panel><PanelBody className="flex items-center gap-2 text-[12.5px] text-tx3"><Spinner /> Loading company profile…</PanelBody></Panel>
      )}
      {company.error ? <Banner tone="err">{errorMessage(company.error)}</Banner> : null}

      {data === null && (
        <Panel>
          <EmptyState
            icon="domain_add"
            title="Set up your company"
            action={
              canEdit ? (
                <Button variant="primary" icon="add" onClick={() => setEditing(true)}>
                  Set up company profile
                </Button>
              ) : undefined
            }
          >
            {canEdit
              ? 'Enter the business identity used on invoices, receipts and throughout MateERP. Legal registration details are optional.'
              : 'An administrator has not set up the company profile yet.'}
          </EmptyState>
        </Panel>
      )}

      {data && (
        <>
          <InfoPanels>
            <InfoPanel
              title="Identity"
              rows={[
                { label: 'Display name', value: data.display_name, strong: true },
                { label: 'Legal name', value: data.legal_name || 'Not registered / not set' },
                { label: 'Registration no.', value: data.registration_number },
                { label: 'Tax identification', value: data.tax_id },
              ]}
            />
            <InfoPanel
              title="Contact"
              rows={[
                { label: 'Address', value: [data.address_line1, data.address_line2, [data.city, data.postal_code].filter(Boolean).join(' '), data.region, data.country].filter(Boolean).join('\n') },
                { label: 'Email', value: data.email },
                { label: 'Phone', value: data.phone },
                { label: 'Website', value: data.website },
              ]}
            />
            <InfoPanel
              title="Financial defaults"
              rows={[
                { label: 'Base currency', value: currencyName(data.base_currency) },
                { label: 'Time zone', value: data.time_zone },
                { label: 'Fiscal year starts', value: MONTHS[data.fiscal_year_start_month - 1] },
                { label: 'Installation model', value: 'One company per deployment' },
              ]}
            />
          </InfoPanels>
          <LogoPanel company={data} canEdit={canEdit || can('branding.manage')} />
          {data.notes && (
            <Panel>
              <PanelHeader title="Business notes" subtitle="Internal — not printed on documents" />
              <PanelBody className="text-[13px] leading-[1.55] whitespace-pre-line text-tx2">{data.notes}</PanelBody>
            </Panel>
          )}
          <p className="m-0 text-[11.5px] text-tx3">Last updated {formatDateTime(data.updated_at)}</p>
        </>
      )}

      {editing && data !== undefined && (
        <CompanyDrawer
          company={data}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            company.mutate(saved);
            invalidate(COMPANY_SUMMARY_KEY);
            invalidate('/branding/');
            setEditing(false);
            toast(data ? 'Company profile saved' : 'Company profile created');
          }}
        />
      )}
    </PageContainer>
  );
}

function LogoPanel({ company, canEdit }: { company: CompanyProfile; canEdit: boolean }) {
  const { mutate } = useCompany();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  const after = (profile: CompanyProfile, message: string) => {
    mutate(profile);
    invalidate(COMPANY_SUMMARY_KEY);
    invalidate('/branding/');
    toast(message);
  };

  const upload = async (file: File) => {
    const problem = checkImage(file);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append('file', file);
    try {
      after(await api.post<CompanyProfile>('/company/logo/', form), company.logo ? 'Logo replaced' : 'Logo uploaded');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel>
      <PanelHeader
        title="Company logo"
        subtitle="Shown in the sidebar and on invoices and receipts. Previous logos stay attached to the branding versions that used them."
        actions={
          canEdit && company.logo ? (
            <Button size="sm" variant="danger" icon="delete" onClick={() => setConfirmRemove(true)}>
              Remove
            </Button>
          ) : null
        }
      />
      <PanelBody className="flex flex-wrap items-center gap-5">
        <div className="flex h-[96px] w-[220px] items-center justify-center border border-bd bg-white p-3">
          {company.logo ? (
            // eslint-disable-next-line @next/next/no-img-element -- private, auth-gated asset
            <img src={company.logo.url} alt={`${company.display_name} logo`} className="max-h-full max-w-full object-contain" />
          ) : (
            <span className="text-[12px] text-[#6B7280]">No logo — initials are used</span>
          )}
        </div>
        {canEdit && (
          <div className="flex min-w-[260px] flex-1 flex-col gap-2">
            <FileDrop label={company.logo ? 'Replace logo' : 'Upload logo'} onFile={upload} busy={busy} />
            {error && <Banner tone="err" compact>{error}</Banner>}
          </div>
        )}
      </PanelBody>
      <ConfirmDialog
        open={confirmRemove}
        title="Remove company logo?"
        confirmLabel="Remove logo"
        danger
        onCancel={() => setConfirmRemove(false)}
        onConfirm={async () => {
          after(await api.delete<CompanyProfile>('/company/logo/'), 'Logo removed');
          setConfirmRemove(false);
        }}
      >
        New documents will use the company initials. Published branding versions keep the logo they
        were published with.
      </ConfirmDialog>
    </Panel>
  );
}
