import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

/*
 * Financial table primitives. Monetary columns use align="right", which also
 * enables tabular numerals so figures line up.
 */

export function Table({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className={cn('w-full border-collapse text-[13px] text-tx', className)}>{children}</table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return <thead className="sticky top-0 z-[1] bg-sf2">{children}</thead>;
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody>{children}</tbody>;
}

export function TR({ className, ...rest }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn('border-b border-bd [tbody_&]:hover:bg-sfh', className)} {...rest} />;
}

type Align = 'left' | 'right' | 'center';
const alignClass: Record<Align, string> = {
  left: 'text-left',
  right: 'text-right tabular-nums',
  center: 'text-center',
};

export function TH({
  align = 'left',
  className,
  ...rest
}: ThHTMLAttributes<HTMLTableCellElement> & { align?: Align }) {
  return (
    <th
      scope="col"
      className={cn(
        'whitespace-nowrap px-3 py-[9px] text-[10.5px] font-semibold uppercase tracking-[.07em] text-tx3',
        alignClass[align],
        className,
      )}
      {...rest}
    />
  );
}

export function TD({
  align = 'left',
  dense,
  className,
  ...rest
}: TdHTMLAttributes<HTMLTableCellElement> & { align?: Align; dense?: boolean }) {
  return (
    <td
      className={cn(dense ? 'px-3 py-[7px]' : 'px-3 py-2.5', alignClass[align], className)}
      {...rest}
    />
  );
}
