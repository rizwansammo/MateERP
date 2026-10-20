import type { ReactNode } from 'react';

import { Wordmark } from '@/components/brand/Wordmark';

/**
 * Full-screen layout for sign-in and password screens. The brand panel
 * reuses the approved splash composition (wordmark, tagline, cyan rule) so
 * authentication feels like part of MateERP, not a generic template.
 */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-bg max-md:flex-col">
      <aside className="relative flex w-[44%] max-w-[620px] flex-col justify-between overflow-hidden border-r border-sb-bd bg-splash-bg px-12 py-10 text-splash-fg max-md:w-full max-md:max-w-none max-md:border-r-0 max-md:border-b max-md:px-6 max-md:py-6">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-[.35]"
          style={{
            backgroundImage:
              'linear-gradient(var(--sbBd) 1px, transparent 1px), linear-gradient(90deg, var(--sbBd) 1px, transparent 1px)',
            backgroundSize: '64px 64px',
            maskImage: 'linear-gradient(135deg, rgba(0,0,0,.9), transparent 70%)',
          }}
        />
        <div className="relative text-[11px] uppercase tracking-[.42em] text-sb-tx2 max-md:hidden">
          Enterprise Resource Planning
        </div>
        <div className="relative flex flex-col gap-[22px] max-md:gap-3">
          <div className="text-[56px] leading-none max-lg:text-[46px] max-md:text-[32px]">
            <Wordmark />
          </div>
          <div className="relative h-0.5 w-[220px] overflow-hidden bg-sb-bd max-md:hidden">
            <div className="absolute inset-y-0 left-0 w-[30%] bg-brand" />
          </div>
          <p className="m-0 max-w-[380px] text-[13px] leading-[1.6] text-sb-tx max-md:hidden">
            Finance, billing, documents and operations for a single company — with every
            change permission-checked and audited.
          </p>
        </div>
        <div className="relative text-[11px] tracking-[.04em] text-sb-faint max-md:hidden">
          A NetaMate product
        </div>
      </aside>
      <main className="flex flex-1 items-center justify-center px-4 py-10">{children}</main>
    </div>
  );
}

export function AuthCard({ eyebrow, title, description, children }: {
  eyebrow: string;
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex w-[400px] max-w-full flex-col gap-5 border border-bd bg-sf p-8 max-sm:p-6">
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[.1em] text-tx3">
          <span aria-hidden="true" className="h-0.5 w-3.5 bg-ac" />
          {eyebrow}
        </div>
        <h1 className="m-0 text-[24px] font-semibold leading-[1.15] tracking-[-.015em] text-tx">{title}</h1>
        {description && <p className="m-0 text-[13px] leading-[1.55] text-tx2">{description}</p>}
      </div>
      {children}
    </div>
  );
}
