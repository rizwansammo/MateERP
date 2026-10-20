'use client';

import { useSyncExternalStore } from 'react';

import { Icon } from './Icon';

export type ToastTone = 'ok' | 'err' | 'warn' | 'info';

interface ToastItem {
  id: number;
  tone: ToastTone;
  message: string;
}

let items: ToastItem[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

/** Show a toast. Only call after an operation actually succeeded or failed. */
export function toast(message: string, tone: ToastTone = 'ok', durationMs = 4200) {
  const id = nextId++;
  items = [...items, { id, tone, message }].slice(-4);
  emit();
  window.setTimeout(() => {
    items = items.filter((t) => t.id !== id);
    emit();
  }, durationMs);
}

const style: Record<ToastTone, { icon: string; color: string }> = {
  ok: { icon: 'check_circle', color: 'var(--ok)' },
  err: { icon: 'error', color: 'var(--err)' },
  warn: { icon: 'warning', color: 'var(--warn)' },
  info: { icon: 'info', color: 'var(--ac)' },
};

/** Toast stack (prototype: bottom-right, tip colours, 3px tone edge). */
export function Toaster() {
  const list = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => items,
    () => items,
  );
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed right-4 bottom-4 z-[95] flex flex-col items-end gap-2"
    >
      {list.map((t) => (
        <div
          key={t.id}
          role={t.tone === 'err' ? 'alert' : 'status'}
          className="pointer-events-auto flex max-w-[440px] min-w-[280px] animate-rise items-start gap-2.5 bg-tip-bg px-3.5 py-[11px] text-[12.5px] leading-[1.45] text-tip-fg shadow-[0_14px_40px_rgba(0,0,0,.3)]"
          style={{ borderLeft: `3px solid ${style[t.tone].color}` }}
        >
          <Icon name={style[t.tone].icon} size={18} className="flex-none" />
          <span className="flex-1">{t.message}</span>
        </div>
      ))}
    </div>
  );
}
