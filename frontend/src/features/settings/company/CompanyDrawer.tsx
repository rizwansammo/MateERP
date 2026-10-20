'use client';

import { type FormEvent, useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field } from '@/components/ui/Field';
import { Input, Select, Textarea } from '@/components/ui/Input';
import { Cell, DialogActions, DialogFooter, Drawer, FormGrid, FormSection } from '@/components/ui/Overlay';
import { api } from '@/lib/api/client';
import { useCurrencies, useTimeZones } from '@/lib/api/hooks';
import type { CompanyProfile } from '@/lib/api/types';
import { MONTHS } from '@/lib/format';
import { useFormState, useUnsavedGuard } from '@/lib/forms';

export type CompanyForm = Omit<CompanyProfile, 'logo' | 'created_at' | 'updated_at'>;

const EMPTY: CompanyForm = {
  display_name: '',
  legal_name: '',
  email: '',
  phone: '',
  website: '',
  address_line1: '',
  address_line2: '',
  city: '',
  region: '',
  postal_code: '',
  country: '',
  tax_id: '',
  registration_number: '',
  base_currency: 'BDT',
  time_zone: 'Asia/Dhaka',
  fiscal_year_start_month: 1,
  notes: '',
};

export function toForm(company: CompanyProfile | null): CompanyForm {
  if (!company) return EMPTY;
  return Object.fromEntries(
    (Object.keys(EMPTY) as (keyof CompanyForm)[]).map((key) => [key, company[key]]),
  ) as unknown as CompanyForm;
}

interface Props {
  company: CompanyProfile | null;
  onClose: () => void;
  onSaved: (company: CompanyProfile) => void;
}

/** Create (first-time setup) or edit the single company profile. */
export function CompanyDrawer({ company, onClose, onSaved }: Props) {
  const form = useFormState<CompanyForm>(toForm(company));
  const { values, set, errors, dirty } = form;
  const currencies = useCurrencies();
  const zones = useTimeZones();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  useUnsavedGuard(dirty);

  const requestClose = () => (dirty ? setConfirmDiscard(true) : onClose());

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (submitting) return;
    if (!values.display_name.trim()) {
      form.setErrors({ display_name: 'Enter the company’s display name.' });
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const saved = company
        ? await api.put<CompanyProfile>('/company/', values)
        : await api.post<CompanyProfile>('/company/', values);
      form.reset(toForm(saved));
      onSaved(saved);
    } catch (err) {
      setError(form.applyError(err));
    } finally {
      setSubmitting(false);
    }
  }

  const text = (key: keyof CompanyForm, label: string, w: 'full' | 'half' | 'third' = 'half', props: Record<string, unknown> = {}) => (
    <Cell w={w}>
      <Field label={label} htmlFor={`co-${key}`} error={errors[key]} required={key === 'display_name'}>
        <Input
          id={`co-${key}`}
          value={String(values[key] ?? '')}
          invalid={Boolean(errors[key])}
          onChange={(e) => set(key, e.target.value as never)}
          {...props}
        />
      </Field>
    </Cell>
  );

  return (
    <>
      <Drawer
        open
        onClose={requestClose}
        eyebrow="Single company"
        title={company ? 'Company profile' : 'Set up company profile'}
        description="Registration details are optional — MateERP supports unregistered businesses."
        footer={
          <DialogFooter>
            <Banner tone="info" compact>
              Changes apply to newly generated documents. Issued invoices and receipts keep the details they
              were issued with. Base currency and fiscal year can be changed until financial records exist.
            </Banner>
            {error && <Banner tone="err" compact>{error}</Banner>}
            <DialogActions>
              <Button onClick={requestClose}>Cancel</Button>
              <Button variant="primary" onClick={() => void submit()} disabled={submitting || (!!company && !dirty)}>
                {submitting ? 'Saving…' : company ? 'Save changes' : 'Create company profile'}
              </Button>
            </DialogActions>
          </DialogFooter>
        }
      >
        <form noValidate onSubmit={submit}>
          <FormGrid>
            <FormSection title="Company information" />
            {text('display_name', 'Display name', 'half', { 'data-autofocus': true, maxLength: 120 })}
            {text('legal_name', 'Legal name (if registered)', 'half', { maxLength: 200 })}
            {text('registration_number', 'Registration number', 'half', { maxLength: 60 })}
            {text('tax_id', 'Tax identification', 'half', { maxLength: 60 })}

            <FormSection title="Business address" />
            {text('address_line1', 'Address line 1', 'full', { maxLength: 200 })}
            {text('address_line2', 'Address line 2', 'full', { maxLength: 200 })}
            {text('city', 'City', 'half', { maxLength: 100 })}
            {text('region', 'State / region', 'half', { maxLength: 100 })}
            {text('postal_code', 'Postal code', 'half', { maxLength: 20 })}
            {text('country', 'Country', 'half', { maxLength: 100 })}

            <FormSection title="Contact details" />
            {text('email', 'Business email', 'half', { type: 'email', maxLength: 254 })}
            {text('phone', 'Phone', 'half', { type: 'tel', maxLength: 40 })}
            {text('website', 'Website', 'full', { type: 'url', placeholder: 'https://', maxLength: 200 })}

            <FormSection title="Financial defaults" />
            <Cell w="third">
              <Field label="Base currency" htmlFor="co-currency" error={errors.base_currency}>
                <Select id="co-currency" value={values.base_currency} onChange={(e) => set('base_currency', e.target.value)}>
                  {(currencies.data ?? [{ code: values.base_currency, name: '' }]).map((c) => (
                    <option key={c.code} value={c.code}>{c.code}{c.name ? ` — ${c.name}` : ''}</option>
                  ))}
                </Select>
              </Field>
            </Cell>
            <Cell w="third">
              <Field label="Time zone" htmlFor="co-tz" error={errors.time_zone}>
                <Select id="co-tz" value={values.time_zone} onChange={(e) => set('time_zone', e.target.value)}>
                  {(zones.data ?? [{ name: values.time_zone }]).map((z) => (
                    <option key={z.name} value={z.name}>{z.name}</option>
                  ))}
                </Select>
              </Field>
            </Cell>
            <Cell w="third">
              <Field label="Fiscal year starts" htmlFor="co-fy" error={errors.fiscal_year_start_month}>
                <Select id="co-fy" value={values.fiscal_year_start_month} onChange={(e) => set('fiscal_year_start_month', Number(e.target.value))}>
                  {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </Select>
              </Field>
            </Cell>
            <Cell>
              <Field label="Business notes (internal)" htmlFor="co-notes" error={errors.notes} hint="Not printed on any document.">
                <Textarea id="co-notes" rows={3} maxLength={2000} value={values.notes} onChange={(e) => set('notes', e.target.value)} />
              </Field>
            </Cell>
          </FormGrid>
        </form>
      </Drawer>
      <ConfirmDialog
        open={confirmDiscard}
        title="Discard unsaved changes?"
        confirmLabel="Discard changes"
        danger
        onCancel={() => setConfirmDiscard(false)}
        onConfirm={() => {
          setConfirmDiscard(false);
          onClose();
        }}
      >
        Your edits to the company profile have not been saved.
      </ConfirmDialog>
    </>
  );
}
