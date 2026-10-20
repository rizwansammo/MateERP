import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  eyebrow?: string;
  description?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ title, eyebrow, description, actions }: PageHeaderProps) {
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
