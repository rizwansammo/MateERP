'use client';

import Link from 'next/link';

import { Icon } from '@/components/ui/Icon';
import { useCompanySummary } from '@/lib/api/hooks';
import { useAuth } from '@/lib/auth/AuthProvider';

/**
 * The customer company's identity (not MateERP's product brand). Shows the
 * uploaded logo or a cyan initials tile, as in the prototype.
 */
export function CompanyCard() {
  const { data } = useCompanySummary();
  const { can } = useAuth();

  const frame =
    'mx-3 mt-3 mb-1 flex items-center gap-2.5 border border-sb-bd bg-sb-card px-3 py-2.5 compact:hidden';

  if (!data?.configured) {
    const body = (
      <>
        <div className="flex size-[30px] flex-none items-center justify-center bg-sb-h text-sb-tx2">
          <Icon name="domain" size={17} />
        </div>
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-[12.5px] font-semibold text-splash-fg">
            {data ? 'Company not configured' : 'Loading company…'}
          </span>
          <span className="text-[10.5px] text-sb-tx2">
            {data && can('company.edit') ? 'Set up company profile →' : 'Single-company installation'}
          </span>
        </div>
      </>
    );
    return data && can('company.edit') ? (
      <Link href="/settings/company" className={`${frame} hover:bg-sb-h hover:no-underline`} data-testid="company-card">
        {body}
      </Link>
    ) : (
      <div className={frame} data-testid="company-card">{body}</div>
    );
  }

  return (
    <div className={frame} data-testid="company-card" title={data.legal_name ?? data.display_name ?? undefined}>
      {data.logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- private, auth-gated asset
        <img src={data.logo_url} alt="" className="size-[30px] flex-none bg-white object-contain p-0.5" />
      ) : (
        <div className="flex size-[30px] flex-none items-center justify-center bg-brand text-[12px] font-bold text-brand-ink">
          {data.initials}
        </div>
      )}
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-[12.5px] font-semibold text-splash-fg">{data.display_name}</span>
        <span className="truncate text-[10.5px] text-sb-tx2">{data.location ?? 'Single-company installation'}</span>
      </div>
    </div>
  );
}
