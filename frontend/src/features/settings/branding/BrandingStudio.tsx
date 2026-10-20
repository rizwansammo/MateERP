'use client';

import { type ReactNode, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox, Segmented } from '@/components/ui/Choice';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field } from '@/components/ui/Field';
import { FileDrop, checkImage } from '@/components/ui/FileDrop';
import { Icon } from '@/components/ui/Icon';
import { Input, Select, Textarea } from '@/components/ui/Input';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import { COMPANY_SUMMARY_KEY } from '@/lib/api/hooks';
import { invalidate } from '@/lib/api/query';
import type { BrandingConfig, BrandingOverview, CompanyProfile, PublishResult } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { cn } from '@/lib/cn';
import { useUnsavedGuard } from '@/lib/forms';

import { CompanySeal } from '@/features/documents/CompanySeal';
import { DarkSegmented, ScaledPage, ViewerToolbar, ZoomControl } from '@/features/documents/DocumentStage';
import { type DocumentBranding, InvoiceDocument } from '@/features/documents/InvoiceDocument';
import { ReceiptDocument } from '@/features/documents/ReceiptDocument';
import { toMoneyFormat } from '@/features/documents/money';
import { sampleInvoice } from '@/features/documents/sample';

import { PublishDialog } from './PublishDialog';

const TEMPLATES: { value: BrandingConfig['invoice_template']; label: string; note: string }[] = [
  { value: 'meridian', label: 'Meridian', note: 'Brand band and bold title' },
  { value: 'ledger', label: 'Ledger', note: 'Classic tax-invoice rules' },
  { value: 'atlas', label: 'Atlas', note: 'Brand-colour sidebar' },
];

const COLOR_PRESETS = ['#0B2A4A', '#1F2937', '#0A78B5', '#00B0F0', '#0E7A4E', '#7C3AED', '#B45309', '#BF2A30'];

type Doc = 'invoice' | 'receipt';

interface StudioProps {
  overview: BrandingOverview;
  onChange: (overview: BrandingOverview) => void;
  onClose: () => void;
  initialDoc?: Doc;
}

export function BrandingStudio({ overview, onChange, onClose, initialDoc = 'invoice' }: StudioProps) {
  const { can } = useAuth();
  const [config, setConfig] = useState<BrandingConfig>(overview.draft.config);
  const [saved, setSaved] = useState<BrandingConfig>(overview.draft.config);
  const [doc, setDoc] = useState<Doc>(initialDoc);
  const [zoom, setZoom] = useState(0.75);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const dirty = JSON.stringify(config) !== JSON.stringify(saved);
  useUnsavedGuard(dirty);

  const set = <K extends keyof BrandingConfig>(key: K, value: BrandingConfig[K]) =>
    setConfig((c) => ({ ...c, [key]: value }));
  const setSeal = (patch: Partial<BrandingConfig['seal']>) => setConfig((c) => ({ ...c, seal: { ...c.seal, ...patch } }));

  const apply = (next: BrandingOverview, keepLocal = false) => {
    onChange(next);
    if (!keepLocal) {
      setConfig(next.draft.config);
      setSaved(next.draft.config);
    }
  };

  async function saveDraft(): Promise<boolean> {
    setSaving(true);
    setError(null);
    try {
      apply(await api.put<BrandingOverview>('/branding/draft/', { config }));
      toast('Draft saved — documents are unchanged until you publish');
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function uploadAsset(kind: 'signature' | 'seal', file: File) {
    const problem = checkImage(file);
    if (problem) return setError(problem);
    const form = new FormData();
    form.append('file', file);
    try {
      const next = await api.post<BrandingOverview>(`/branding/draft/assets/${kind}/`, form);
      onChange(next);
      if (kind === 'seal') setSeal({ mode: 'image' });
      toast(kind === 'seal' ? 'Seal image added to the draft' : 'Signature added to the draft');
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function removeAsset(kind: 'signature' | 'seal') {
    try {
      onChange(await api.delete<BrandingOverview>(`/branding/draft/assets/${kind}/`));
      if (kind === 'seal' && config.seal.mode === 'image') setSeal({ mode: 'none' });
      toast(kind === 'seal' ? 'Seal image removed from the draft' : 'Signature removed from the draft');
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function uploadLogo(file: File) {
    const problem = checkImage(file);
    if (problem) return setError(problem);
    const form = new FormData();
    form.append('file', file);
    try {
      await api.post<CompanyProfile>('/company/logo/', form);
      invalidate(COMPANY_SUMMARY_KEY);
      invalidate('/company/');
      apply(await api.get<BrandingOverview>('/branding/'), true);
      toast('Company logo updated');
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const branding: DocumentBranding | null = useMemo(() => {
    if (!overview.company) return null;
    return {
      config,
      company: overview.company,
      logoUrl: overview.company.logo_url ?? null,
      signatureUrl: overview.draft.signature_url,
      sealImageUrl: overview.draft.seal_image_url,
    };
  }, [config, overview]);

  const sample = useMemo(() => sampleInvoice(overview.company?.base_currency ?? 'BDT'), [overview.company]);
  const format = toMoneyFormat(overview.display);
  const busy = saving || publishing;
  const pending = overview.pending_request;

  return createPortal(
    <div role="dialog" aria-modal="true" aria-label="Branding editor" className="fixed inset-0 z-[70] flex flex-col bg-[#0A0E13] text-[#E6EDF5]">
      <ViewerToolbar
        icon="palette"
        title="Invoice & receipt branding — editor"
        subtitle={dirty ? 'Unsaved changes in this editor' : overview.has_unpublished_changes ? 'Draft saved · not yet published' : 'Draft matches the published version'}
        onClose={() => (dirty ? setConfirmClose(true) : onClose())}
      >
        <DarkSegmented label="Preview document" value={doc} onChange={setDoc} options={[{ value: 'invoice', label: 'Invoice' }, { value: 'receipt', label: 'Receipt' }]} />
        <ZoomControl zoom={zoom} onZoom={setZoom} />
        <button
          type="button"
          onClick={() => void saveDraft()}
          disabled={!dirty || busy}
          className="h-[30px] border border-[#2A3644] bg-transparent px-3 text-[12px] font-medium text-[#E6EDF5] hover:bg-[#121A24] disabled:opacity-40"
        >
          {saving ? 'Saving…' : 'Save draft'}
        </button>
        <button
          type="button"
          onClick={async () => {
            if (dirty && !(await saveDraft())) return;
            setPublishing(true);
          }}
          disabled={busy || Boolean(pending) || !overview.company}
          title={pending ? 'A publication is already waiting for approval' : undefined}
          className="h-[30px] border border-brand bg-brand px-3 text-[12px] font-semibold text-brand-ink hover:brightness-[1.08] disabled:opacity-40"
        >
          {overview.approval_required ? 'Submit for approval' : 'Publish'}
        </button>
      </ViewerToolbar>

      <div className="flex min-h-0 flex-1 max-lg:flex-col">
        <aside aria-label="Branding settings" className="w-[400px] flex-none overflow-auto border-r border-bd bg-sf text-tx max-lg:max-h-[50vh] max-lg:w-full max-lg:border-r-0 max-lg:border-b">
          {error && <div className="p-4 pb-0"><Banner tone="err" compact action={<button type="button" aria-label="Dismiss" onClick={() => setError(null)} className="bg-transparent text-tx3"><Icon name="close" size={16} /></button>}>{error}</Banner></div>}
          {!overview.company && <div className="p-4 pb-0"><Banner tone="warn" compact>Set up the company profile before publishing. The preview uses its name, address and logo.</Banner></div>}
          {pending && <div className="p-4 pb-0"><Banner tone="warn" compact>“{pending.title}” is waiting for approval. You can keep editing the draft; publishing is paused until it is decided.</Banner></div>}

          <Section title="Invoice template">
            <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Invoice template">
              {TEMPLATES.map((t) => {
                const active = config.invoice_template === t.value;
                return (
                  <button
                    key={t.value}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => set('invoice_template', t.value)}
                    className={cn('flex flex-col gap-1.5 border bg-sf p-1.5 text-left', active ? 'border-ac outline outline-1 outline-ac' : 'border-bd hover:border-bd2')}
                  >
                    <div className="h-[150px] overflow-hidden border border-bd bg-white">
                      {branding && (
                        <div aria-hidden="true" className="pointer-events-none origin-top-left" style={{ transform: 'scale(0.135)', width: 794 }}>
                          <InvoiceDocument branding={{ ...branding, config: { ...config, invoice_template: t.value } }} invoice={sample} number={overview.numbering.next_invoice} />
                        </div>
                      )}
                    </div>
                    <span className="flex items-center justify-between text-[12px] font-semibold">
                      {t.label}
                      {active && <Icon name="check_circle" size={15} className="text-ac" />}
                    </span>
                    <span className="text-[10.5px] leading-tight text-tx3">{t.note}</span>
                  </button>
                );
              })}
            </div>
          </Section>

          <Section title="Colours">
            <div className="grid grid-cols-2 gap-3">
              <ColorField id="brand" label="Brand colour" value={config.brand_color} onChange={(v) => set('brand_color', v)} />
              <ColorField id="accent" label="Accent colour" value={config.accent_color} onChange={(v) => set('accent_color', v)} />
            </div>
            <div className="flex flex-wrap gap-1.5" aria-label="Colour presets">
              {COLOR_PRESETS.map((c) => (
                <button key={c} type="button" title={`Use ${c} as brand colour`} aria-label={`Brand colour ${c}`} onClick={() => set('brand_color', c)} className="size-6 border border-bd2" style={{ background: c }} />
              ))}
            </div>
          </Section>

          <Section title="Layout & typography">
            <Field label="Header layout" htmlFor="b-header">
              <Segmented label="Header layout" value={config.header_layout} onChange={(v) => set('header_layout', v)} options={[{ value: 'logo-left', label: 'Logo left' }, { value: 'logo-right', label: 'Logo right' }, { value: 'centered', label: 'Centred' }]} size="sm" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Typography" htmlFor="b-font">
                <Select id="b-font" value={config.typography} onChange={(e) => set('typography', e.target.value as BrandingConfig['typography'])}>
                  <option value="sans">Plex Sans</option>
                  <option value="serif">Plex Serif</option>
                  <option value="mono">Sans + mono figures</option>
                </Select>
              </Field>
              <Field label="Spacing" htmlFor="b-spacing">
                <Select id="b-spacing" value={config.spacing} onChange={(e) => set('spacing', e.target.value as BrandingConfig['spacing'])}>
                  <option value="compact">Compact</option>
                  <option value="regular">Regular</option>
                  <option value="airy">Airy</option>
                </Select>
              </Field>
            </div>
            <Field label="Table style" htmlFor="b-table">
              <Segmented label="Table style" value={config.table_style} onChange={(v) => set('table_style', v)} options={[{ value: 'lined', label: 'Lined' }, { value: 'striped', label: 'Striped' }, { value: 'boxed', label: 'Boxed' }]} size="sm" />
            </Field>
            <Field label={`Logo height — ${config.logo_size}px`} htmlFor="b-logo-size">
              <input id="b-logo-size" type="range" min={24} max={120} step={2} value={config.logo_size} onChange={(e) => set('logo_size', Number(e.target.value))} className="w-full accent-[var(--ac)]" />
            </Field>
          </Section>

          <Section title="Company logo">
            <p className="m-0 text-[11.5px] leading-normal text-tx3">
              Shared with the company profile. Changing it updates the sidebar now; documents use it from the next publication.
            </p>
            <div className="flex h-[70px] items-center justify-center border border-bd bg-white p-2">
              {overview.company?.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element -- private asset
                <img src={overview.company.logo_url} alt="Company logo" className="max-h-full max-w-full object-contain" />
              ) : (
                <span className="text-[12px] text-[#6B7280]">No logo — initials are used</span>
              )}
            </div>
            {(can('company.edit') || can('branding.manage')) && overview.company && (
              <FileDrop label={overview.company.logo_url ? 'Replace logo' : 'Upload logo'} onFile={(f) => void uploadLogo(f)} />
            )}
          </Section>

          <Section title="Text & payment details">
            <Field label="Payment instructions" htmlFor="b-pay" hint="Bank or mobile-banking details printed on invoices.">
              <Textarea id="b-pay" rows={4} maxLength={1000} value={config.payment_instructions} onChange={(e) => set('payment_instructions', e.target.value)} />
            </Field>
            <Field label="Terms & conditions" htmlFor="b-terms">
              <Textarea id="b-terms" rows={3} maxLength={2000} value={config.terms} onChange={(e) => set('terms', e.target.value)} />
            </Field>
            <Field label="Footer text" htmlFor="b-footer">
              <Input id="b-footer" maxLength={200} value={config.footer_text} onChange={(e) => set('footer_text', e.target.value)} />
            </Field>
            <CustomFields value={config.custom_fields} onChange={(v) => set('custom_fields', v)} />
          </Section>

          <Section title="Authorised signature">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Signatory name" htmlFor="b-sig-name">
                <Input id="b-sig-name" maxLength={80} value={config.signature_name} onChange={(e) => set('signature_name', e.target.value)} />
              </Field>
              <Field label="Title" htmlFor="b-sig-title">
                <Input id="b-sig-title" maxLength={80} value={config.signature_title} onChange={(e) => set('signature_title', e.target.value)} />
              </Field>
            </div>
            <AssetRow
              label="Signature image"
              url={overview.draft.signature_url}
              hint="Without an image the name is shown in a script face."
              onUpload={(f) => void uploadAsset('signature', f)}
              onRemove={() => void removeAsset('signature')}
            />
            <Checkbox checked={config.show_signature_on_invoice} onChange={(v) => set('show_signature_on_invoice', v)} label="Show signature on invoices" />
            <Checkbox checked={config.show_signature_on_receipt} onChange={(v) => set('show_signature_on_receipt', v)} label="Show signature on money receipts" />
            <p className="m-0 text-[11.5px] text-tx3">A signature image is a document branding asset — not proof that a signed-in user electronically signed a document.</p>
          </Section>

          <Section title="Company seal (receipts)">
            <Segmented label="Seal type" value={config.seal.mode} onChange={(mode) => setSeal({ mode })} options={[{ value: 'editor', label: 'Stamp editor' }, { value: 'image', label: 'Upload image' }, { value: 'none', label: 'No seal' }]} size="sm" />
            {config.seal.mode === 'editor' && (
              <div className="flex gap-3">
                <div className="grid flex-1 grid-cols-2 gap-3">
                  <Field label="Top arc text" htmlFor="b-seal-top">
                    <Input id="b-seal-top" maxLength={30} value={config.seal.top} onChange={(e) => setSeal({ top: e.target.value.toUpperCase() })} />
                  </Field>
                  <Field label="Bottom arc text" htmlFor="b-seal-bottom">
                    <Input id="b-seal-bottom" maxLength={26} value={config.seal.bottom} onChange={(e) => setSeal({ bottom: e.target.value.toUpperCase() })} />
                  </Field>
                  <Field label="Centre text" htmlFor="b-seal-center">
                    <Input id="b-seal-center" maxLength={9} value={config.seal.center} onChange={(e) => setSeal({ center: e.target.value.toUpperCase() })} />
                  </Field>
                  <Field label="Shape" htmlFor="b-seal-shape">
                    <Select id="b-seal-shape" value={config.seal.shape} onChange={(e) => setSeal({ shape: e.target.value as 'circle' | 'square' })}>
                      <option value="circle">Circle</option>
                      <option value="square">Square</option>
                    </Select>
                  </Field>
                  <div className="col-span-2">
                    <ColorField id="seal" label="Ink colour" value={config.seal.color} onChange={(color) => setSeal({ color })} />
                  </div>
                </div>
                <div className="flex w-[96px] flex-none items-center justify-center border border-bd bg-white" aria-hidden="true">
                  <CompanySeal seal={config.seal} size={84} />
                </div>
              </div>
            )}
            {config.seal.mode === 'image' && (
              <AssetRow label="Seal image" url={overview.draft.seal_image_url} hint="A transparent PNG works best." onUpload={(f) => void uploadAsset('seal', f)} onRemove={() => void removeAsset('seal')} />
            )}
            <p className="m-0 text-[11.5px] text-tx3">A visual company stamp for money receipts — not a legally certified digital signature.</p>
          </Section>

          <Section title="Money receipt">
            <Segmented label="Receipt template" value={config.receipt_template} onChange={(v) => { set('receipt_template', v); setDoc('receipt'); }} options={[{ value: 'official', label: 'Official (framed)' }, { value: 'compact', label: 'Compact' }]} size="sm" />
            <Field label="Payment confirmation text" htmlFor="b-r-confirm">
              <Textarea id="b-r-confirm" rows={3} maxLength={500} value={config.receipt_confirmation} onChange={(e) => set('receipt_confirmation', e.target.value)} />
            </Field>
            <Field label="Receipt footer" htmlFor="b-r-footer">
              <Input id="b-r-footer" maxLength={300} value={config.receipt_footer} onChange={(e) => set('receipt_footer', e.target.value)} />
            </Field>
            <Checkbox checked={config.show_logo_on_receipt} onChange={(v) => set('show_logo_on_receipt', v)} label="Show company logo on receipts" />
          </Section>
        </aside>

        <div className="flex min-h-0 flex-1 flex-col items-center gap-3 overflow-auto p-8 max-sm:p-4">
          <div className="flex items-center gap-2 text-[11px] text-[#8794A6]">
            <Icon name="visibility" size={15} />
            Live preview with fictional sample data — nothing is issued or recorded.
          </div>
          {branding ? (
            doc === 'invoice' ? (
              <ScaledPage width={794} height={1123} scale={zoom} label="Invoice preview">
                <InvoiceDocument branding={branding} invoice={sample} number={overview.numbering.next_invoice} format={format} taxLabel={overview.display.tax_label} watermark="PREVIEW" />
              </ScaledPage>
            ) : (
              <ScaledPage width={794} height={600} scale={zoom} label="Money receipt preview">
                <ReceiptDocument branding={branding} invoice={sample} invoiceNumber={overview.numbering.next_invoice} receiptNumber={overview.numbering.next_receipt} format={format} watermark="PREVIEW" />
              </ScaledPage>
            )
          ) : (
            <div className="mt-20 max-w-[380px] text-center text-[13px] text-[#8794A6]">The preview needs the company profile (name and address). Set it up in Settings → Company Profile.</div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmClose}
        title="Close without saving?"
        confirmLabel="Discard edits"
        danger
        onCancel={() => setConfirmClose(false)}
        onConfirm={() => {
          setConfirmClose(false);
          onClose();
        }}
      >
        Edits made in this editor have not been saved to the draft.
      </ConfirmDialog>
      <PublishDialog
        open={publishing}
        approvalRequired={overview.approval_required}
        onCancel={() => setPublishing(false)}
        onDone={(result: PublishResult, next: BrandingOverview) => {
          setPublishing(false);
          apply(next);
          toast(result.status === 'published' ? `Published as version ${result.version.number}` : 'Submitted for approval — not published yet');
          if (result.status === 'published') onClose();
        }}
      />
    </div>,
    document.body,
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3 border-b border-bd p-4">
      <h3 className="m-0 flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[.1em] text-tx3">
        <span aria-hidden="true" className="h-0.5 w-3.5 bg-ac" />
        {title}
      </h3>
      {children}
    </section>
  );
}

function ColorField({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (v: string) => void }) {
  const [text, setText] = useState(value);
  const [prev, setPrev] = useState(value);
  if (prev !== value) {
    setPrev(value);
    setText(value);
  }
  const valid = /^#[0-9a-fA-F]{6}$/.test(text);
  return (
    <Field label={label} htmlFor={`c-${id}`} error={valid ? undefined : 'Use #RRGGBB'}>
      <div className="flex gap-1.5">
        <input type="color" aria-label={`${label} picker`} value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} className="h-[34px] w-[38px] flex-none cursor-pointer border border-bd bg-inp p-0.5" />
        <Input
          id={`c-${id}`}
          value={text}
          maxLength={7}
          invalid={!valid}
          className="font-mono"
          onChange={(e) => {
            const next = e.target.value.toUpperCase();
            setText(next);
            if (/^#[0-9A-F]{6}$/.test(next)) onChange(next);
          }}
        />
      </div>
    </Field>
  );
}

function CustomFields({ value, onChange }: { value: BrandingConfig['custom_fields']; onChange: (v: BrandingConfig['custom_fields']) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11.5px] font-medium text-tx2">Custom fields (e.g. BIN, trade licence)</span>
      {value.map((f, i) => (
        <div key={i} className="flex gap-1.5">
          <Input aria-label={`Custom field ${i + 1} label`} placeholder="Label" maxLength={40} value={f.label} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
          <Input aria-label={`Custom field ${i + 1} value`} placeholder="Value" maxLength={80} value={f.value} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
          <button type="button" aria-label={`Remove custom field ${i + 1}`} onClick={() => onChange(value.filter((_, j) => j !== i))} className="flex w-[34px] flex-none items-center justify-center border border-bd bg-transparent text-tx3 hover:text-err">
            <Icon name="close" size={16} />
          </button>
        </div>
      ))}
      {value.length < 6 && (
        <button type="button" onClick={() => onChange([...value, { label: '', value: '' }])} className="flex h-7 w-fit items-center gap-1 border border-dashed border-bd2 bg-transparent px-2.5 text-[12px] font-medium text-lk">
          <Icon name="add" size={16} /> Add field
        </button>
      )}
    </div>
  );
}

function AssetRow({ label, url, hint, onUpload, onRemove }: { label: string; url: string | null; hint: string; onUpload: (f: File) => void; onRemove: () => void }) {
  return (
    <div className="flex flex-col gap-2">
      {url ? (
        <div className="flex items-center gap-3 border border-bd bg-sf2 p-2">
          {/* eslint-disable-next-line @next/next/no-img-element -- private asset */}
          <img src={url} alt={label} className="h-12 w-28 bg-white object-contain" />
          <span className="flex-1 text-[12px] text-tx2">{label} in draft</span>
          <Button size="sm" variant="danger" icon="delete" onClick={onRemove}>Remove</Button>
        </div>
      ) : null}
      <FileDrop label={url ? `Replace ${label.toLowerCase()}` : `Upload ${label.toLowerCase()}`} hint={hint} onFile={onUpload} />
    </div>
  );
}
