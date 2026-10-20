'use client';

import { useState } from 'react';
import { Banner } from '@/components/ui/Banner';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { api } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { FormDrawer, type FormValues } from '@/features/commerce/forms';
import { KIND_LABEL, today, useApi } from '@/features/commerce/shared';
import type { DocumentKind, FiledDocument } from '@/features/commerce/types';

interface References { parties: { value: string; label: string }[]; invoice_id?: { value: string; label: string }[]; payment_id?: { value: string; label: string }[]; vendor_bill_id?: { value: string; label: string }[]; expense_id?: { value: string; label: string }[]; vendor_payment_id?: { value: string; label: string }[] }

export function UploadDrawer({ area, initial = {}, onClose }: {
  area: 'client' | 'vendor'; initial?: FormValues; onClose: () => void;
}) {
  const { can } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [party, setParty] = useState(String(initial[area === 'client' ? 'customer_id' : 'vendor_id'] ?? ''));
  const [lookup, setLookup] = useState('');
  const params = new URLSearchParams({ area, party, search: lookup });
  for (const key of ['invoice_id', 'payment_id', 'vendor_bill_id', 'expense_id', 'vendor_payment_id']) if (initial[key]) params.set(key, String(initial[key]));
  const references = useApi<References>(`/documents/references/?${params}`);
  const choices = (key: 'invoice_id' | 'payment_id' | 'vendor_bill_id' | 'expense_id' | 'vendor_payment_id') => [{ value: '', label: 'None' }, ...(references.data?.[key] ?? [])];
  const kinds: DocumentKind[] = area === 'client'
    ? ['client_supporting', ...(can('banking.evidence.view') ? ['bank_proof' as const] : [])]
    : ['vendor_invoice', 'vendor_receipt', 'vendor_supporting'];
  return <FormDrawer title="Upload document" eyebrow={`${area} documents`} onClose={onClose}
    initial={{ kind: kinds[0] ?? 'client_supporting', title: '', document_date: today(), notes: '', customer_id: '', vendor_id: '', invoice_id: '', payment_id: '', vendor_bill_id: '', expense_id: '', vendor_payment_id: '', ...initial }}
    extraDirty={file !== null} saveLabel="Upload" success="Document securely stored"
    onValues={values => setParty(String(values[area === 'client' ? 'customer_id' : 'vendor_id']))}
    fields={[
      { key: 'kind', label: 'Document type', type: 'select', options: kinds.map(k => ({ value: k, label: KIND_LABEL[k] })) },
      { key: area === 'client' ? 'customer_id' : 'vendor_id', label: area === 'client' ? 'Customer' : 'Vendor', type: 'select', required: true,
        options: [{ value: '', label: 'Select…' }, ...(references.data?.parties ?? [])] },
      { key: 'title', label: 'Title' }, { key: 'document_date', label: 'Document date', type: 'date', required: true },
      ...(area === 'client' ? [{ key: 'invoice_id', label: 'Invoice', type: 'select' as const, options: choices('invoice_id') }, { key: 'payment_id', label: 'Customer payment', type: 'select' as const, options: choices('payment_id') }]
        : [{ key: 'vendor_bill_id', label: 'Vendor bill', type: 'select' as const, options: choices('vendor_bill_id') }, { key: 'expense_id', label: 'Expense', type: 'select' as const, options: choices('expense_id') }, { key: 'vendor_payment_id', label: 'Vendor payment', type: 'select' as const, options: choices('vendor_payment_id') }]),
      { key: 'notes', label: 'Notes', type: 'textarea' },
    ]}
    onSave={async values => {
      if (!file) throw new Error('Select a PDF, PNG, JPEG or WEBP file.');
      const data = new FormData();
      data.set('file', file);
      for (const [key, value] of Object.entries(values)) if (value !== '' && key !== (area === 'client' ? 'vendor_id' : 'customer_id')) data.set(key, String(value));
      return api.post<FiledDocument>('/documents/', data);
    }}>
    <div className="mt-4 flex flex-col gap-3 border border-dashed border-bd2 bg-sf2 p-4" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); setFile(e.dataTransfer.files[0] ?? null); }}>
      <Field label={area === 'client' ? 'Find customer' : 'Find vendor'} htmlFor="filing-search" hint="Search names when the party is not in the recent choices."><Input id="filing-search" value={lookup} onChange={e => setLookup(e.target.value)} /></Field>
      <Field label="File" htmlFor="upload-file" required hint="Drop a file here or browse. PDF, PNG, JPEG or WEBP; maximum 10 MB. The server validates content.">
        <Input id="upload-file" aria-label="File" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)} />
      </Field>
      {file && <span className="text-[12px] text-tx2">{file.name}</span>}
      <Banner tone="info">Bank payment proofs are internal evidence. Generated invoices and receipts appear automatically; you do not need to upload them.</Banner>
    </div>
  </FormDrawer>;
}
