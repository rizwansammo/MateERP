import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

export type Tone = 'ok' | 'warn' | 'err' | 'info' | 'neutral' | 'accent';

const tones: Record<Tone, string> = {
  ok: 'bg-oks text-ok',
  warn: 'bg-warns text-warn',
  err: 'bg-errs text-err',
  info: 'bg-infos text-info',
  neutral: 'bg-neus text-neu',
  accent: 'bg-infos text-ac',
};

/** Status badge: 20px, uppercase, square tone dot. */
export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      data-tone={tone}
      className={cn(
        'inline-flex h-5 items-center gap-[5px] whitespace-nowrap px-[7px] text-[10.5px] font-semibold uppercase tracking-[.04em]',
        tones[tone],
      )}
    >
      <span aria-hidden="true" className="size-[5px] bg-current" />
      {children}
    </span>
  );
}
