import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

import { Icon } from './Icon';

export interface Stat {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: string;
  /** Colour of the value and of the 2px top accent bar. */
  tone?: 'default' | 'ok' | 'warn' | 'err' | 'accent';
  /** Cyan top bar with a neutral value (prototype "accent" KPI). */
  accentBar?: boolean;
}

const valueTone: Record<NonNullable<Stat['tone']>, string> = {
  default: 'text-tx',
  ok: 'text-ok',
  warn: 'text-warn',
  err: 'text-err',
  accent: 'text-ac',
};

const barTone: Record<NonNullable<Stat['tone']>, string> = {
  default: 'bg-transparent',
  ok: 'bg-ok',
  warn: 'bg-warn',
  err: 'bg-err',
  accent: 'bg-ac',
};

/** KPI strip: a shared-border grid of stat tiles. */
export function StatGrid({
  stats,
  minWidth = 190,
  small = false,
  balancedSeven = false,
}: {
  stats: Stat[];
  minWidth?: number;
  /** Seven equal-width cards per row on desktop; preserves full grid width. */
  balancedSeven?: boolean;
  /** 18px values, as used for configuration summaries. */
  small?: boolean;
}) {
  return (
    <div
      className={cn('grid border-l border-t border-bd', balancedSeven && 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-7')}
      style={balancedSeven ? undefined : { gridTemplateColumns: `repeat(auto-fit, minmax(${minWidth}px, 1fr))` }}
    >
      {stats.map((stat) => {
        const tone = stat.tone ?? 'default';
        return (
          <div
            key={stat.label}
            className="relative flex min-w-0 flex-col gap-1.5 border-b border-r border-bd bg-sf px-[18px] pt-4 pb-[15px]"
          >
            <div
              className={cn('absolute left-0 top-0 h-0.5 w-full', stat.accentBar ? 'bg-ac' : barTone[tone])}
            />
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-[10.5px] font-semibold uppercase tracking-[.08em] text-tx3">
                {stat.label}
              </span>
              {stat.icon && <Icon name={stat.icon} size={17} className="text-tx3" />}
            </div>
            <div
              className={cn(
                'truncate font-semibold tracking-[-.015em] tabular-nums',
                small ? 'text-[18px]' : 'text-[22px]',
                valueTone[tone],
              )}
            >
              {stat.value}
            </div>
            <div className="min-h-4 truncate text-[11.5px] text-tx3">{stat.sub}</div>
          </div>
        );
      })}
    </div>
  );
}
