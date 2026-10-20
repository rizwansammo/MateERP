'use client';

import { type ReactNode, useState } from 'react';

import { Banner } from './Banner';
import { Button } from './Button';
import { Field } from './Field';
import { Textarea } from './Input';
import { DialogActions, DialogFooter, Modal } from './Overlay';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  /** Ask for a reason (required when ``reasonRequired``). */
  reason?: 'optional' | 'required';
  reasonLabel?: string;
  onCancel: () => void;
  /** Return a promise; errors are shown in the dialog and keep it open. */
  onConfirm: (reason: string) => Promise<unknown> | void;
}

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  danger,
  reason,
  reasonLabel = 'Reason',
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    if (busy) return;
    setText('');
    setError(null);
    onCancel();
  };

  const confirm = async () => {
    if (reason === 'required' && !text.trim()) {
      setError('Give a reason.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onConfirm(text.trim());
      setText('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The action failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title={title}
      footer={
        <DialogFooter>
          {error && <Banner tone="err" compact>{error}</Banner>}
          <DialogActions>
            <Button onClick={close} disabled={busy}>Cancel</Button>
            <Button variant={danger ? 'danger' : 'primary'} onClick={confirm} disabled={busy} data-autofocus>
              {busy ? 'Working…' : confirmLabel}
            </Button>
          </DialogActions>
        </DialogFooter>
      }
    >
      <div className="flex flex-col gap-4 text-[13px] leading-[1.55] text-tx2">
        {children}
        {reason && (
          <Field label={reasonLabel} htmlFor="confirm-reason" required={reason === 'required'}>
            <Textarea id="confirm-reason" rows={3} maxLength={500} value={text} onChange={(e) => setText(e.target.value)} />
          </Field>
        )}
      </div>
    </Modal>
  );
}
