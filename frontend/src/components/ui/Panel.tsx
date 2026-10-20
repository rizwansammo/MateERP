import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cn('flex min-w-0 flex-col border border-bd bg-sf', className)}>{children}</section>;
}

interface PanelHeaderProps {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

export function PanelHeader({ title, subtitle, actions }: PanelHeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-bd px-3.5 py-3">
      <div className="flex min-w-0 flex-col gap-0.5">
        <h2 className="m-0 text-[13.5px] font-semibold text-tx">{title}</h2>
        {subtitle && <div className="text-[12px] text-tx3">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function PanelBody({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn('p-3.5', className)}>{children}</div>;
}
