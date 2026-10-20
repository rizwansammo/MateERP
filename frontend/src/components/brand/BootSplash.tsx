'use client';

import { useSyncExternalStore } from 'react';

import { Wordmark } from './Wordmark';

const noop = () => () => {};

/**
 * Branded opening screen. It is server-rendered so it is the first thing
 * painted, and it disappears as soon as the client has hydrated. There is
 * no artificial minimum duration.
 */
export function BootSplash() {
  const hydrated = useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
  if (hydrated) return null;

  return (
    <div
      data-testid="boot-splash"
      aria-hidden="true"
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-[22px] bg-splash-bg text-splash-fg"
    >
      <div className="text-[64px] max-sm:text-[44px]">
        <Wordmark />
      </div>
      <div className="text-[11px] uppercase tracking-[.42em] text-sb-tx2">
        Enterprise Resource Planning
      </div>
      <div className="relative h-0.5 w-[220px] overflow-hidden bg-sb-bd">
        <div className="absolute inset-y-0 left-0 w-[30%] animate-load bg-brand" />
      </div>
      <div className="absolute bottom-7 text-[11px] tracking-[.04em] text-sb-faint">
        A NetaMate product
      </div>
    </div>
  );
}
