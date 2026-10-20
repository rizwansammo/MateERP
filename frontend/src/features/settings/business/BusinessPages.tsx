'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox, Segmented } from '@/components/ui/Choice';
import { Field } from '@/components/ui/Field';
import { AmountInput, Input, Select } from '@/components/ui/Input';
import { InfoPanel, InfoPanels } from '@/components/ui/InfoPanel';
import { Cell, DialogActions, DialogFooter, Drawer, FormGrid } from '@/components/ui/Overlay';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader } from '@/components/ui/Panel';
import { Spinner } from '@/components/ui/Spinner';
import { toast } from '@/components/ui/Toast';
import { ApiError, api, errorMessage } from '@/lib/api/client';
import { useCurrencies, useTimeZones } from '@/lib/api/hooks';
import { invalidate, useQuery } from '@/lib/api/query';
import type { BusinessSettings, CompanyProfile } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { cn } from '@/lib/cn';
import { MONTHS } from '@/lib/format';
import { useFormState } from '@/lib/forms';

import { formatMinor } from '@/features/documents/money';
import { renderNumber } from '@/features/documents/numbering';

import { Gate } from '../Gate';
import { RatesPanel } from '@/features/accounting/PeriodsTaxFx';
import { NUMBERING_LABELS, NumberingDrawer } from '../NumberingDrawer';

const READERS = ['company.view', 'company.edit', 'branding.manage'];

function useBusiness() {
  return useQuery('/settings/business/', () => api.get<BusinessSettings>('/settings/business/'));
}

function useCompanyOrNull() {
  return useQuery('/company/', async () => {
    try {
      return await api.get<CompanyProfile>('/company/');
    } catch (error) {
      if (error instanceof ApiError && error.code === 'company_not_configured') return null;
      throw error;
    }
  });
}

function Loading() {
  return <div className="flex items-center gap-2 text-[12.5px] text-tx3"><Spinner /> Loading settings…</div>;
}

function NoCompany() {
  return (
    <Banner tone="warn" action={<Link href="/settings/company" className="text-[12.5px] font-medium">Set up company</Link>}>
      Base currency, time zone and fiscal year are part of the company profile, which has not been set up yet.
    </Banner>
  );
}

// --- Financial settings -------------------------------------------------------------

export function FinancialSettingsPage() {
  return <Gate anyOf={READERS}><FinancialContent /></Gate>;
}

function FinancialContent() {
  const { can } = useAuth();
  const company = useCompanyOrNull();
  const business = useBusiness();
  const currencies = useCurrencies();
  const [editing, setEditing] = useState(false);
  const [numbering, setNumbering] = useState(false);
  const today = new Date();

  if (company.loading && company.data === undefined) return <PageContainer><Loading /></PageContainer>;
  const co = company.data;
  const currencyName = currencies.data?.find((c) => c.code === co?.base_currency)?.name;

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Settings"
        title="Financial settings"
        description="Fiscal year, base currency and reference number formats used by the accounting and document modules."
        actions={co && can('company.edit') ? <Button variant="primary" icon="edit" onClick={() => setEditing(true)}>Edit financial defaults</Button> : null}
      />
      <Banner tone="info">
        Accounting periods and the general ledger enforce posting rules. Once financial records exist, base
        currency and fiscal year start are locked so history is never rewritten.
      </Banner>
      {co === null && <NoCompany />}
      {company.error ? <Banner tone="err">{errorMessage(company.error)}</Banner> : null}
      <InfoPanels>
        {co && (
          <InfoPanel title="Fiscal" rows={[
            { label: 'Fiscal year', value: `${MONTHS[co.fiscal_year_start_month - 1]} – ${MONTHS[(co.fiscal_year_start_month + 10) % 12]}` },
            { label: 'Base currency', value: `${co.base_currency}${currencyName ? ` — ${currencyName}` : ''}` },
            { label: 'Time zone', value: co.time_zone },
            { label: 'Rounding', value: 'Exact decimals, per-currency minor units' },
          ]} />
        )}
        {business.data && (
          <InfoPanel
            title="Reference number formats"
            action={can('company.edit') ? <Button size="sm" icon="edit" onClick={() => setNumbering(true)}>Edit</Button> : undefined}
            rows={Object.entries(NUMBERING_LABELS).map(([key, label]) => ({
              label,
              value: <span className="font-mono text-[12px]">{business.data!.numbering[key]} <span className="text-tx3">→ {renderNumber(business.data!.numbering[key] ?? '', today, 1)}</span></span>,
            }))}
          />
        )}
      </InfoPanels>
      {editing && co && (
        <FinancialDrawer company={co} onClose={() => setEditing(false)} onSaved={(saved) => { company.mutate(saved); invalidate('/branding/'); setEditing(false); toast('Financial defaults saved'); }} />
      )}
      {numbering && business.data && (
        <NumberingDrawer numbering={business.data.numbering} onClose={() => setNumbering(false)} onSaved={(s) => { business.mutate(s); invalidate('/branding/'); setNumbering(false); toast('Number formats saved'); }} />
      )}
    </PageContainer>
  );
}

function FinancialDrawer({ company, onClose, onSaved }: { company: CompanyProfile; onClose: () => void; onSaved: (c: CompanyProfile) => void }) {
  const form = useFormState({ base_currency: company.base_currency, time_zone: company.time_zone, fiscal_year_start_month: company.fiscal_year_start_month });
  const currencies = useCurrencies();
  const zones = useTimeZones();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.patch<CompanyProfile>('/company/', form.values));
    } catch (err) {
      setError(form.applyError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer open onClose={onClose} width={520} eyebrow="Financial settings" title="Financial defaults"
      footer={<DialogFooter>{error && <Banner tone="err" compact>{error}</Banner>}<DialogActions><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy || !form.dirty} onClick={() => void save()}>{busy ? 'Saving…' : 'Save'}</Button></DialogActions></DialogFooter>}>
      <FormGrid>
        <Cell>
          <Field label="Base currency" htmlFor="f-cur" error={form.errors.base_currency}>
            <Select id="f-cur" value={form.values.base_currency} onChange={(e) => form.set('base_currency', e.target.value)}>
              {(currencies.data ?? []).map((c) => <option key={c.code} value={c.code}>{c.code} — {c.name}</option>)}
            </Select>
          </Field>
        </Cell>
        <Cell>
          <Field label="Time zone" htmlFor="f-tz" error={form.errors.time_zone}>
            <Select id="f-tz" value={form.values.time_zone} onChange={(e) => form.set('time_zone', e.target.value)}>
              {(zones.data ?? [{ name: form.values.time_zone }]).map((z) => <option key={z.name} value={z.name}>{z.name}</option>)}
            </Select>
          </Field>
        </Cell>
        <Cell>
          <Field label="Fiscal year starts" htmlFor="f-fy" error={form.errors.fiscal_year_start_month}>
            <Select id="f-fy" value={form.values.fiscal_year_start_month} onChange={(e) => form.set('fiscal_year_start_month', Number(e.target.value))}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </Select>
          </Field>
        </Cell>
      </FormGrid>
    </Drawer>
  );
}

// --- Currency settings --------------------------------------------------------------

export function CurrencySettingsPage() {
  return <Gate anyOf={READERS}><CurrencyContent /></Gate>;
}

function CurrencyContent() {
  const { can } = useAuth();
  const business = useBusiness();
  const company = useCompanyOrNull();
  const currencies = useCurrencies();
  if (!business.data || company.data === undefined || !currencies.data) return <PageContainer><Loading /></PageContainer>;
  return <CurrencyForm settings={business.data} base={company.data?.base_currency ?? null} currencies={currencies.data} editable={can('company.edit')} onSaved={business.mutate} />;
}

function CurrencyForm({ settings, base, currencies, editable, onSaved }: {
  settings: BusinessSettings;
  base: string | null;
  currencies: { code: string; name: string; symbol: string }[];
  editable: boolean;
  onSaved: (s: BusinessSettings) => void;
}) {
  const form = useFormState({ enabled_currencies: settings.enabled_currencies, currency_display: settings.currency_display, number_grouping: settings.number_grouping });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const baseInfo = currencies.find((c) => c.code === base);
  const sample = formatMinor(12_500_000, form.values.number_grouping);
  const toggle = (code: string) => {
    if (code === base) return;
    const list = form.values.enabled_currencies;
    form.set('enabled_currencies', list.includes(code) ? list.filter((c) => c !== code) : [...list, code]);
  };
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.patch<BusinessSettings>('/settings/business/', form.values);
      form.reset({ enabled_currencies: saved.enabled_currencies, currency_display: saved.currency_display, number_grouping: saved.number_grouping });
      onSaved(saved);
      toast('Currency settings saved');
      invalidate('/accounting/');
    } catch (err) {
      setError(form.applyError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageContainer>
      <PageHeader eyebrow="Settings" title="Currency settings" description="Base currency, the currencies documents may be issued in, and how amounts are displayed." />
      <Banner tone="info">Posted journals preserve their rate snapshots. Changes to rates apply only to new postings.</Banner>
      {base === null && <NoCompany />}
      {error && <Banner tone="err">{error}</Banner>}
      <Panel>
        <PanelHeader title="Base currency" subtitle="Set in the company profile; locks once financial records exist." actions={<Link href="/settings/financial" className="text-[12.5px] font-medium">Change →</Link>} />
        <PanelBody className="text-[13px]">{base ? <><b>{base}</b> — {baseInfo?.name}</> : '—'}</PanelBody>
      </Panel>
      <Panel>
        <PanelHeader title="Enabled transaction currencies" subtitle="Currencies that invoices, bills and payments may use. The base currency is always enabled." />
        <PanelBody>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Enabled currencies">
            {currencies.map((c) => {
              const on = form.values.enabled_currencies.includes(c.code) || c.code === base;
              return (
                <button key={c.code} type="button" aria-pressed={on} disabled={!editable || c.code === base} onClick={() => toggle(c.code)} title={c.name}
                  className={cn('flex h-7 items-center gap-1.5 border px-2.5 text-[12px] font-medium disabled:cursor-default',
                    on ? 'border-pr bg-pr text-prt' : 'border-bd2 bg-sf text-tx2 hover:bg-sf3')}>
                  <span className="font-mono">{c.code}</span><span className={on ? 'opacity-80' : 'text-tx3'}>{c.symbol}</span>
                </button>
              );
            })}
          </div>
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader title="Display" />
        <PanelBody className="flex flex-col gap-4">
          <Field label="Currency shown as" htmlFor="cur-display">
            <Segmented label="Currency shown as" value={form.values.currency_display} onChange={(v) => form.set('currency_display', v)} options={[{ value: 'symbol', label: 'Symbol' }, { value: 'code', label: 'Code' }]} />
          </Field>
          <Field label="Digit grouping" htmlFor="cur-group">
            <Segmented label="Digit grouping" value={form.values.number_grouping} onChange={(v) => form.set('number_grouping', v)} options={[{ value: 'south_asian', label: 'Lakh / crore (12,34,567)' }, { value: 'international', label: 'International (1,234,567)' }]} />
          </Field>
          <div className="text-[12.5px] text-tx2">Example: <span className="font-mono text-tx">{form.values.currency_display === 'symbol' ? `${baseInfo?.symbol ?? ''}${sample}` : `${base ?? ''} ${sample}`}</span></div>
        </PanelBody>
      </Panel>
      {editable && (
        <div className="flex justify-end gap-2">
          <Button variant="primary" onClick={() => void save()} disabled={!form.dirty || busy}>{busy ? 'Saving…' : 'Save currency settings'}</Button>
        </div>
      )}
      <RatesPanel />
    </PageContainer>
  );
}

// --- Tax settings -------------------------------------------------------------------

export function TaxSettingsPage() {
  return <Gate anyOf={READERS}><TaxContent /></Gate>;
}

function TaxContent() {
  const { can } = useAuth();
  const business = useBusiness();
  const company = useCompanyOrNull();
  if (!business.data || company.data === undefined) return <PageContainer><Loading /></PageContainer>;
  return <TaxForm settings={business.data} taxId={company.data?.tax_id ?? ''} editable={can('company.edit')} onSaved={business.mutate} />;
}

function TaxForm({ settings, taxId, editable, onSaved }: { settings: BusinessSettings; taxId: string; editable: boolean; onSaved: (s: BusinessSettings) => void }) {
  const initial = {
    tax_registered: settings.tax_registered,
    tax_label: settings.tax_label,
    tax_registration_label: settings.tax_registration_label,
    default_tax_rate: settings.default_tax_rate ?? '',
    prices_include_tax: settings.prices_include_tax,
  };
  const form = useFormState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    if (form.values.default_tax_rate && !/^\d{1,3}(\.\d{1,2})?$/.test(form.values.default_tax_rate)) {
      form.setErrors({ default_tax_rate: 'Enter a percentage such as 15 or 7.5' });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = await api.patch<BusinessSettings>('/settings/business/', { ...form.values, default_tax_rate: form.values.default_tax_rate || null });
      form.reset({ ...form.values, default_tax_rate: saved.default_tax_rate ?? '' });
      onSaved(saved);
      toast('Tax settings saved');
    } catch (err) {
      setError(form.applyError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <PageContainer>
      <PageHeader eyebrow="Settings" title="Tax settings" description="Tax identification and defaults that future invoices and bills will use." />
      <Banner tone="info">Document tax defaults. Ledger tax mappings and manual adjustments are available in Banking & Accounting → Tax Management. Billing calculations arrive in Phase 4; tax filing is not provided.</Banner>
      {error && <Banner tone="err">{error}</Banner>}
      <InfoPanels>
        <InfoPanel title="Identification" rows={[
          { label: 'Tax identification', value: taxId || 'Not set' },
          { label: 'Change', value: <Link href="/settings/company">Edit in Company Profile →</Link> },
        ]} />
      </InfoPanels>
      <Panel>
        <PanelHeader title="Tax configuration" />
        <PanelBody>
          <FormGrid>
            <Cell><Checkbox checked={form.values.tax_registered} disabled={!editable} onChange={(v) => form.set('tax_registered', v)} label="The company is registered for tax" hint="Leave unticked for unregistered businesses." /></Cell>
            <Cell w="third">
              <Field label="Tax name on documents" htmlFor="t-label" error={form.errors.tax_label} hint="e.g. VAT, GST, Tax">
                <Input id="t-label" disabled={!editable} maxLength={20} value={form.values.tax_label} onChange={(e) => form.set('tax_label', e.target.value)} />
              </Field>
            </Cell>
            <Cell w="third">
              <Field label="Registration label" htmlFor="t-reg" error={form.errors.tax_registration_label} hint="e.g. BIN, TIN, VAT no.">
                <Input id="t-reg" disabled={!editable} maxLength={40} value={form.values.tax_registration_label} onChange={(e) => form.set('tax_registration_label', e.target.value)} />
              </Field>
            </Cell>
            <Cell w="third">
              <Field label="Default rate (%)" htmlFor="t-rate" error={form.errors.default_tax_rate}>
                <AmountInput id="t-rate" disabled={!editable} placeholder="0.00" value={form.values.default_tax_rate} invalid={Boolean(form.errors.default_tax_rate)} onChange={(e) => form.set('default_tax_rate', e.target.value.trim())} />
              </Field>
            </Cell>
            <Cell><Checkbox checked={form.values.prices_include_tax} disabled={!editable} onChange={(v) => form.set('prices_include_tax', v)} label="Catalogue prices include tax" /></Cell>
          </FormGrid>
        </PanelBody>
      </Panel>
      {editable && (
        <div className="flex justify-end">
          <Button variant="primary" onClick={() => void save()} disabled={!form.dirty || busy}>{busy ? 'Saving…' : 'Save tax settings'}</Button>
        </div>
      )}
    </PageContainer>
  );
}
