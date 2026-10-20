'use client';

import { useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { Cell, DialogActions, DialogFooter, Drawer, FormGrid } from '@/components/ui/Overlay';
import { api } from '@/lib/api/client';
import type { BusinessSettings } from '@/lib/api/types';
import { useFormState } from '@/lib/forms';

import { isValidNumberFormat, renderNumber } from '@/features/documents/numbering';

export const NUMBERING_LABELS: Record<string, string> = {
  invoice: 'Invoice',
  receipt: 'Money receipt',
  credit_note: 'Credit note',
  payment: 'Client payment',
  expense: 'Expense',
  vendor_bill: 'Vendor bill',
  purchase_order: 'Purchase order',
  journal: 'Journal entry',
  sales_order: 'Sales order',
  refund: 'Customer refund',
  vendor_payment: 'Vendor payment',
};

export function NumberingDrawer({ numbering, onClose, onSaved }: {
  numbering: Record<string, string>;
  onClose: () => void;
  onSaved: (settings: BusinessSettings) => void;
}) {
  const form = useFormState<Record<string, string>>(numbering);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const today = new Date();

  const save = async () => {
    const local: Record<string, string> = {};
    for (const [key, value] of Object.entries(form.values)) {
      const problem = isValidNumberFormat(value);
      if (problem) local[`numbering.${key}`] = problem;
    }
    form.setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    setError(null);
    try {
      const changed = Object.fromEntries(Object.entries(form.values).filter(([k, v]) => numbering[k] !== v));
      onSaved(await api.patch<BusinessSettings>('/settings/business/', { numbering: changed }));
    } catch (err) {
      setError(form.applyError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer
      open
      onClose={onClose}
      width={560}
      eyebrow="Document numbering"
      title="Number formats"
      description="Tokens: {YYYY} {YY} {MM} and {###} for the sequence (3–8 digits). Each document type needs its own prefix. Existing numbers never change."
      footer={
        <DialogFooter>
          <Banner tone="info" compact>Sequential, collision-safe issuance arrives with each document module (Phases 3–6). These formats are stored now.</Banner>
          {error && <Banner tone="err" compact>{error}</Banner>}
          <DialogActions>
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" onClick={() => void save()} disabled={busy || !form.dirty}>{busy ? 'Saving…' : 'Save formats'}</Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      <FormGrid>
        {Object.keys(NUMBERING_LABELS).map((key) => {
          const value = form.values[key] ?? '';
          const problem = form.errors[`numbering.${key}`];
          return (
            <Cell key={key} w="half">
              <Field label={NUMBERING_LABELS[key]!} htmlFor={`num-${key}`} error={problem} hint={problem ? undefined : `Next: ${isValidNumberFormat(value) ? '—' : renderNumber(value.toUpperCase(), today, 1)}`}>
                <Input id={`num-${key}`} className="font-mono" maxLength={40} value={value} invalid={Boolean(problem)} onChange={(e) => form.set(key, e.target.value.toUpperCase())} />
              </Field>
            </Cell>
          );
        })}
      </FormGrid>
    </Drawer>
  );
}
