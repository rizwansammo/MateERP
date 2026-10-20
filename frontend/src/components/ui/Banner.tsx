import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

import { Icon } from './Icon';

export type BannerTone = 'info' | 'warn' | 'err' | 'ok' | 'neutral';

const tones: Record<BannerTone, { box: string; icon: string; glyph: string }> = {
  info: { box: 'bg-infos border-info', icon: 'text-info', glyph: 'info' },
  warn: { box: 'bg-warns border-warn', icon: 'text-warn', glyph: 'warning' },
  err: { box: 'bg-errs border-err', icon: 'text-err', glyph: 'error' },
  ok: { box: 'bg-oks border-ok', icon: 'text-ok', glyph: 'check_circle' },
  neutral: { box: 'bg-neus border-neu', icon: 'text-neu', glyph: 'info' },
};

interface BannerProps {
  tone?: BannerTone;
  children: ReactNode;
  action?: ReactNode;
  compact?: boolean;
  className?: string;
}

/** Tone banner (prototype: padding 11/14, 18px icon, 12.5px text). */
export function Banner({ tone = 'info', children, action, compact, className }: BannerProps) {
  const t = tones[tone];
  return (
    <div
      role={tone === 'err' ? 'alert' : 'status'}
      className={cn(
        'flex items-start gap-2.5 border text-[12.5px] leading-normal text-tx',
        compact ? 'px-3 py-[9px]' : 'px-3.5 py-[11px]',
        t.box,
        className,
      )}
    >
      <Icon name={t.glyph} size={compact ? 17 : 18} className={t.icon} />
      <div className="min-w-0 flex-1 text-pretty">{children}</div>
      {action}
    </div>
  );
}
