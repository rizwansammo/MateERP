'use client';

import { type ReactNode, useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Choice';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field } from '@/components/ui/Field';
import { AmountInput, Input, Select, Textarea } from '@/components/ui/Input';
import { Cell, DialogActions, DialogFooter, Drawer, FormGrid, FormSection } from '@/components/ui/Overlay';
import { type HeaderMeta, PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { ApiError, errorMessage } from '@/lib/api/client';
import { useFormState, useUnsavedGuard } from '@/lib/forms';

import { refreshCommerce, useApi } from './shared';
import { toast } from '@/components/ui/Toast';

export function Screen({
  eyebrow,
  title,
  description,
  actions,
  meta,
  children,
}: {
  eyebrow: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: HeaderMeta[];
  children?: ReactNode;
}) {
  return (
    <PageContainer>
      <PageHeader eyebrow={eyebrow} title={title} description={description} actions={actions} meta={meta} />
      {children}
    </PageContainer>
  );
}

export interface FieldSpec {
  key: string;
  label: string;
  type?: 'text' | 'email' | 'date' | 'number' | 'amount' | 'textarea' | 'checkbox' | 'select' | 'section';
  options?: { value: string; label: string }[];
  w?: 'full' | 'half' | 'third' | 'twothird';
  required?: boolean;
  hint?: string;
  placeholder?: string;
}

export type FormValues = Record<string, string | boolean>;

/** Drawer form (prototype FormPanel) for commercial records. */
export function FormDrawer({
  title,
  eyebrow,
  description,
  fields,
  initial,
  onSave,
  onClose,
  saveLabel = 'Save',
  success = 'Saved',
  width = 640,
  children,
  extraDirty = false,
  onValues,
}: {
  title: string;
  eyebrow: string;
  description?: ReactNode;
  fields: FieldSpec[];
  initial: FormValues;
  onSave: (values: FormValues) => Promise<unknown>;
  onClose: (result?: unknown) => void;
  saveLabel?: string;
  success?: string | ((result: unknown) => string);
  width?: number;
  children?: ReactNode | ((values: FormValues, set: (key: string, value: string | boolean) => void) => ReactNode);
  extraDirty?: boolean;
  onValues?: (values: FormValues) => void;
}) {
  const form = useFormState<FormValues>(initial);
  const needsCurrency = fields.some(f => f.key === 'currency');
  const defaults = useApi<{ base_currency: string }>(needsCurrency ? '/accounting/config/' : null);
  const values = { ...form.values };
  if (needsCurrency && !values.currency) values.currency = defaults.data?.base_currency ?? '';
  const ready = !needsCurrency || Boolean(values.currency);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [discard, setDiscard] = useState(false);
  const dirty = form.dirty || extraDirty;
  useUnsavedGuard(dirty);
  const set = (key: string, value: string | boolean) => {
    form.set(key, value);
    onValues?.({ ...values, [key]: value });
  };
  const close = () => {
    if (busy) return;
    if (dirty) setDiscard(true);
    else onClose();
  };
  const save = async () => {
    if (busy || !ready) return;
    setBusy(true);
    setError(null);
    try {
      const result = await onSave(values);
      refreshCommerce();
      toast(typeof success === 'function' ? success(result) : success);
      onClose(result);
    } catch (e) {
      const message = form.applyError(e);
      const hidden =
        e instanceof ApiError
          ? Object.entries(e.fieldErrors())
              .filter(([name]) => !fields.some((f) => f.key === name))
              .map(([, value]) => value)
              .join(' · ')
          : '';
      setError(hidden || message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Drawer
        open
        title={title}
        eyebrow={eyebrow}
        description={description}
        width={width}
        onClose={close}
        footer={
          <DialogFooter>
            {error && <Banner tone="err">{error}</Banner>}
            {needsCurrency && Boolean(defaults.error) && !ready && <Banner tone="err">Unable to load company currency defaults. {errorMessage(defaults.error)}</Banner>}
            <DialogActions>
              <Button disabled={busy} onClick={close}>
                Cancel
              </Button>
              <Button variant="primary" disabled={busy || !ready} onClick={() => void save()}>
                {busy ? 'Saving…' : saveLabel}
              </Button>
            </DialogActions>
          </DialogFooter>
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <FormGrid>
            {fields.map((f) =>
              f.type === 'section' ? (
                <FormSection key={f.key} title={f.label} />
              ) : (
                <Cell key={f.key} w={f.w ?? (f.type === 'textarea' ? 'full' : 'half')}>
                  {f.type === 'checkbox' ? (
                    <Checkbox checked={Boolean(values[f.key])} onChange={(v) => set(f.key, v)} label={f.label} hint={f.hint} />
                  ) : (
                    <Field label={f.label} htmlFor={`cf-${f.key}`} required={f.required} hint={f.hint} error={form.errors[f.key]}>
                      {f.type === 'select' ? (
                        <Select id={`cf-${f.key}`} aria-label={f.label} value={String(values[f.key] ?? '')} onChange={(e) => set(f.key, e.target.value)}>
                          {(f.options ?? []).map((o) => (
                            <option key={o.value} value={o.value}>
                              {o.label}
                            </option>
                          ))}
                        </Select>
                      ) : f.type === 'textarea' ? (
                        <Textarea id={`cf-${f.key}`} aria-label={f.label} rows={2} placeholder={f.placeholder} value={String(values[f.key] ?? '')} onChange={(e) => set(f.key, e.target.value)} />
                      ) : f.type === 'amount' ? (
                        <AmountInput id={`cf-${f.key}`} aria-label={f.label} placeholder={f.placeholder} value={String(values[f.key] ?? '')} onChange={(e) => set(f.key, e.target.value)} />
                      ) : (
                        <Input
                          id={`cf-${f.key}`}
                          aria-label={f.label}
                          type={f.type === 'date' ? 'date' : f.type === 'email' ? 'email' : f.type === 'number' ? 'number' : 'text'}
                          placeholder={f.placeholder}
                          value={String(values[f.key] ?? '')}
                          onChange={(e) => set(f.key, e.target.value)}
                        />
                      )}
                    </Field>
                  )}
                </Cell>
              ),
            )}
          </FormGrid>
          {typeof children === 'function' ? children(values, set) : children}
        </form>
      </Drawer>
      <ConfirmDialog
        open={discard}
        title="Discard unsaved changes?"
        confirmLabel="Discard"
        danger
        onCancel={() => setDiscard(false)}
        onConfirm={() => onClose()}
      />
    </>
  );
}

/** Values → API body: empty optional strings become null for *_id fields, numbers stay numbers. */
export function body(values: FormValues, numbers: string[] = []) {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(values)) {
    if (k.endsWith('_id') && k !== 'tax_id') out[k] = v === '' ? null : Number(v);
    else if (numbers.includes(k)) out[k] = v === '' ? 0 : Number(v);
    else out[k] = v;
  }
  return out;
}
