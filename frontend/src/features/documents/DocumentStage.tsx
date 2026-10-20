'use client';

import type { ReactNode } from 'react';

import { Icon } from '@/components/ui/Icon';
import { cn } from '@/lib/cn';

/*
 * Dark document-viewer chrome from the prototype (background #0A0E13,
 * 54px toolbar #0D131B, #2A3644 control borders).
 */

export const ZOOM_STEPS = [0.5, 0.6, 0.75, 0.9, 1, 1.25] as const;

export function ViewerToolbar({ icon = 'description', title, subtitle, children, onClose }: {
  icon?: string;
  title: string;
  subtitle?: ReactNode;
  children?: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="flex h-[54px] flex-none items-center gap-3 border-b border-[#1D2733] bg-[#0D131B] px-3.5 max-sm:gap-2">
      <Icon name={icon} size={22} className="text-brand max-sm:hidden" />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-[13.5px] font-semibold">{title}</span>
        {subtitle && <span className="truncate text-[11px] text-[#8794A6]">{subtitle}</span>}
      </div>
      {children}
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="flex size-[30px] flex-none items-center justify-center border border-[#2A3644] bg-transparent text-[#C9D3DF] hover:text-white"
      >
        <Icon name="close" size={18} />
      </button>
    </div>
  );
}

export function DarkSegmented<T extends string>({ value, options, onChange, label }: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex h-[30px] border border-[#2A3644]">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            'border-r border-[#2A3644] px-3 text-[12px] font-medium last:border-r-0',
            o.value === value ? 'bg-[#E6EDF5] text-[#0A0E13]' : 'bg-transparent text-[#C9D3DF] hover:text-white',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ZoomControl({ zoom, onZoom }: { zoom: number; onZoom: (z: number) => void }) {
  const index = ZOOM_STEPS.findIndex((z) => z >= zoom);
  const at = index === -1 ? ZOOM_STEPS.length - 1 : index;
  const btn = 'flex size-6 items-center justify-center bg-transparent text-[#C9D3DF] hover:text-white disabled:opacity-40';
  return (
    <div className="flex h-[30px] items-center gap-1 border border-[#2A3644] px-1 max-md:hidden">
      <button type="button" className={btn} aria-label="Zoom out" disabled={at === 0} onClick={() => onZoom(ZOOM_STEPS[Math.max(0, at - 1)]!)}>
        <Icon name="remove" size={18} />
      </button>
      <span className="min-w-14 text-center font-mono text-[12px] font-medium">{Math.round(zoom * 100)}%</span>
      <button type="button" className={btn} aria-label="Zoom in" disabled={at === ZOOM_STEPS.length - 1} onClick={() => onZoom(ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, at + 1)]!)}>
        <Icon name="add" size={18} />
      </button>
    </div>
  );
}

/** Scales a fixed-size document without clipping layout. */
export function ScaledPage({ width, height, scale, children, label }: {
  width: number;
  height: number;
  scale: number;
  children: ReactNode;
  label: string;
}) {
  return (
    <div
      role="img"
      aria-label={label}
      className="flex-none shadow-[0_24px_70px_rgba(0,0,0,.5)]"
      style={{ width: width * scale, height: height * scale }}
    >
      <div style={{ width, transform: `scale(${scale})`, transformOrigin: 'top left' }}>{children}</div>
    </div>
  );
}
