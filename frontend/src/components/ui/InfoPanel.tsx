import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

export interface InfoRow {
  label: string;
  value: ReactNode;
  strong?: boolean;
  tone?: 'ok' | 'warn' | 'err' | 'muted';
  onClick?: () => void;
}

const toneClass = { ok: 'text-ok', warn: 'text-warn', err: 'text-err', muted: 'text-tx3' } as const;

/** Grid of label/value panels (prototype settings "P" panels). */
export function InfoPanels({ children, min = 300 }: { children: ReactNode; min?: number }) {
  return (
    <div
      className="grid gap-[18px]"
      style={{ gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${min}px), 1fr))` }}
    >
      {children}
    </div>
  );
}

interface InfoPanelProps {
  title: string;
  rows: InfoRow[];
  action?: ReactNode;
}

export function InfoPanel({ title, rows, action }: InfoPanelProps) {
  return (
    <section className="min-w-0 border border-bd bg-sf">
      <header className="flex items-center justify-between gap-2 border-b border-bd px-4 py-3">
        <h2 className="m-0 text-[13px] font-semibold text-tx">{title}</h2>
        {action}
      </header>
      <dl className="m-0 px-4 pt-1.5 pb-3">
        {rows.map((row) => {
          const empty = row.value === null || row.value === undefined || row.value === '';
          return (
            <div key={row.label} className="flex justify-between gap-3.5 border-b border-bd py-[7px] text-[12.5px]">
              <dt className="flex-none text-tx3">{row.label}</dt>
              <dd
                className={cn(
                  'm-0 min-w-0 text-right whitespace-pre-line break-words tabular-nums',
                  row.strong ? 'font-semibold' : 'font-normal',
                  empty ? 'text-tx3' : row.tone ? toneClass[row.tone] : 'text-tx',
                )}
              >
                {row.onClick ? (
                  <button type="button" onClick={row.onClick} className="bg-transparent text-right text-lk hover:text-ac hover:underline">
                    {empty ? '—' : row.value}
                  </button>
                ) : empty ? (
                  '—'
                ) : (
                  row.value
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
