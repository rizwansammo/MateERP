import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

export interface HeaderMeta {
  label: string;
  value: ReactNode;
  tone?: 'ok' | 'warn' | 'err';
}

interface PageHeaderProps {
  title: string;
  eyebrow?: string;
  description?: ReactNode;
  actions?: ReactNode;
  /** Label/value facts under the description (prototype PageHead meta). */
  meta?: HeaderMeta[];
}

const metaTone = { ok: 'text-ok', warn: 'text-warn', err: 'text-err' } as const;

export function PageHeader({ title, eyebrow, description, actions, meta }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="flex min-w-0 max-w-[760px] flex-col gap-1.5">
        {eyebrow && (
          <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[.1em] text-tx3">
            <span aria-hidden="true" className="h-0.5 w-3.5 bg-ac" />
            {eyebrow}
          </div>
        )}
        <h1 className="m-0 text-[24px] font-semibold leading-[1.15] tracking-[-.015em] text-tx">
          {title}
        </h1>
        {description && (
          <p className="m-0 text-[13px] leading-[1.55] text-pretty text-tx2">{description}</p>
        )}
        {meta && meta.length > 0 && (
          <div className="mt-0.5 flex flex-wrap gap-x-[18px] gap-y-1.5">
            {meta.map((m) => (
              <div key={m.label} className="flex items-center gap-1.5 text-[12px] text-tx2">
                <span className="text-tx3">{m.label}</span>
                <span className={cn('font-medium', m.tone ? metaTone[m.tone] : 'text-tx')}>{m.value}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

/** Standard page content container (padding 24/28/56, max width 1640). */
export function PageContainer({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-[1640px] flex-col gap-[18px] px-4 pt-6 pb-14 md:px-7">
      {children}
    </div>
  );
}
