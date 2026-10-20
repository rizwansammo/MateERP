'use client';

import { useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Input, Textarea } from '@/components/ui/Input';
import { DialogActions, DialogFooter, Modal } from '@/components/ui/Overlay';
import { api, errorMessage } from '@/lib/api/client';
import type { BrandingOverview, PublishResult } from '@/lib/api/types';

interface Props {
  open: boolean;
  approvalRequired: boolean;
  onCancel: () => void;
  onDone: (result: PublishResult, overview: BrandingOverview) => void;
  /** Restore a historical version instead of publishing the draft. */
  restoreVersion?: number;
}

export function PublishDialog({ open, approvalRequired, onCancel, onDone, restoreVersion }: Props) {
  const [label, setLabel] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = restoreVersion
        ? await api.post<PublishResult>(`/branding/versions/${restoreVersion}/restore/`)
        : await api.post<PublishResult>('/branding/publish/', { label, reason });
      const overview = await api.get<BrandingOverview>('/branding/');
      setLabel('');
      setReason('');
      onDone(result, overview);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const action = approvalRequired ? 'Submit for approval' : restoreVersion ? 'Restore as new version' : 'Publish';
  return (
    <Modal
      open={open}
      onClose={() => !busy && onCancel()}
      eyebrow="Invoice & receipt branding"
      title={restoreVersion ? `Restore version ${restoreVersion}` : approvalRequired ? 'Submit branding for approval' : 'Publish branding'}
      description={
        restoreVersion
          ? 'The historical configuration is copied into the draft and published as a new version. History is never rewritten.'
          : 'Publishing creates a new immutable version. New documents use it; previously issued invoices and receipts keep their original appearance.'
      }
      footer={
        <DialogFooter>
          {approvalRequired && (
            <Banner tone="warn" compact>An approval rule applies. The branding is published only after an authorised approver accepts the request.</Banner>
          )}
          {error && <Banner tone="err" compact>{error}</Banner>}
          <DialogActions>
            <Button onClick={onCancel} disabled={busy}>Cancel</Button>
            <Button variant="primary" onClick={() => void submit()} disabled={busy} data-autofocus>
              {busy ? 'Working…' : action}
            </Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      {!restoreVersion && (
        <div className="flex flex-col gap-4">
          <Field label="Version label (optional)" htmlFor="pub-label" hint="For example “2027 identity refresh”.">
            <Input id="pub-label" maxLength={80} value={label} onChange={(e) => setLabel(e.target.value)} />
          </Field>
          {approvalRequired && (
            <Field label="Note for the approver" htmlFor="pub-reason">
              <Textarea id="pub-reason" rows={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
          )}
        </div>
      )}
    </Modal>
  );
}
