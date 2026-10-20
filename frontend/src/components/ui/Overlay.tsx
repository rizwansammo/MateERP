'use client';

import { type ReactNode, useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

import { cn } from '@/lib/cn';

import { Icon } from './Icon';

/*
 * Drawer and Modal share the prototype's form-panel anatomy: an eyebrow,
 * a 19px title, a scrolling body and an --sf2 footer. Both trap focus,
 * close on Escape and restore focus to the opener.
 */

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function useDialogBehaviour(open: boolean, onClose: () => void) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const first = panel?.querySelector<HTMLElement>('[data-autofocus]') ??
      panel?.querySelector<HTMLElement>(FOCUSABLE);
    first?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        closeRef.current();
        return;
      }
      if (event.key !== 'Tab' || !panel) return;
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (!items.length) return;
      const firstItem = items[0]!;
      const lastItem = items[items.length - 1]!;
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      opener?.focus?.();
    };
  }, [open]);

  return panelRef;
}

interface DialogHeaderProps {
  titleId: string;
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  onClose: () => void;
}

function DialogHeader({ titleId, eyebrow, title, description, onClose }: DialogHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-bd px-6 pt-5 pb-4 max-sm:px-4">
      <div className="flex min-w-0 flex-col gap-1">
        {eyebrow && (
          <div className="text-[10.5px] font-semibold uppercase tracking-[.09em] text-ac">{eyebrow}</div>
        )}
        <h2 id={titleId} className="m-0 text-[19px] font-semibold tracking-[-.01em] text-tx">
          {title}
        </h2>
        {description && (
          <div className="max-w-[620px] text-[12.5px] leading-normal text-pretty text-tx2">{description}</div>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="flex size-8 flex-none items-center justify-center border border-bd bg-transparent text-tx2 hover:bg-sf3"
      >
        <Icon name="close" size={18} />
      </button>
    </div>
  );
}

export function DialogFooter({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 border-t border-bd bg-sf2 px-6 py-3.5 max-sm:px-4">{children}</div>
  );
}

export function DialogActions({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap justify-end gap-2">{children}</div>;
}

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  eyebrow?: string;
  description?: ReactNode;
  width?: number;
  footer?: ReactNode;
  children: ReactNode;
}

/** Right-hand form drawer (prototype FormPanel). */
export function Drawer({ open, onClose, title, eyebrow, description, width = 640, footer, children }: DrawerProps) {
  const titleId = useId();
  const panelRef = useDialogBehaviour(open, onClose);
  if (!open) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-[80] flex justify-end bg-scrim"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex h-full max-w-[100vw] flex-col border-l border-bd2 bg-sf shadow-[-24px_0_60px_rgba(0,0,0,.28)]"
        style={{ width }}
      >
        <DialogHeader titleId={titleId} eyebrow={eyebrow} title={title} description={description} onClose={onClose} />
        <div className="flex-1 overflow-auto px-6 pt-5 pb-6 max-sm:px-4">{children}</div>
        {footer}
      </div>
    </div>,
    document.body,
  );
}

interface ModalProps extends Omit<DrawerProps, 'width'> {
  width?: number;
  tone?: 'default' | 'dark';
}

/** Centred dialog for confirmations and one-time information. */
export function Modal({ open, onClose, title, eyebrow, description, width = 460, footer, children }: ModalProps) {
  const titleId = useId();
  const panelRef = useDialogBehaviour(open, onClose);
  if (!open) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center overflow-auto bg-scrim px-4 pt-[12vh] pb-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn('flex max-w-full animate-rise flex-col border border-bd2 bg-sf shadow-[0_30px_80px_rgba(0,0,0,.35)]')}
        style={{ width }}
      >
        <DialogHeader titleId={titleId} eyebrow={eyebrow} title={title} description={description} onClose={onClose} />
        {children && <div className="px-6 pt-5 pb-5 max-sm:px-4">{children}</div>}
        {footer}
      </div>
    </div>,
    document.body,
  );
}

/** 12-column form grid used inside drawers (prototype field widths). */
export function FormGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-12 gap-x-3.5 gap-y-4">{children}</div>;
}

const spans = {
  full: 'col-span-12',
  half: 'col-span-12 sm:col-span-6',
  third: 'col-span-12 sm:col-span-4',
  twothird: 'col-span-12 sm:col-span-8',
} as const;

export function Cell({ w = 'full', children }: { w?: keyof typeof spans; children: ReactNode }) {
  return <div className={spans[w]}>{children}</div>;
}

export function FormSection({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="col-span-12 mt-1 flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[.1em] text-tx3 first:mt-0">
      <span aria-hidden="true" className="h-0.5 w-3.5 bg-ac" />
      {title}
      {children}
    </div>
  );
}
