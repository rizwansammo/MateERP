import { cn } from '@/lib/cn';

/*
 * The MateERP software wordmark (not the customer company's logo).
 * Proportions from the approved reference: large "M", smaller "ATE" at
 * 0.667em, large cyan "ERP", all in the supplied Optimus display face. Size it with the
 * parent's font-size.
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      role="img"
      aria-label="MateERP"
      className={cn(
        'inline-flex items-baseline whitespace-nowrap font-wordmark font-normal leading-none tracking-normal',
        className,
      )}
    >
      <span aria-hidden="true" className="text-[1em]">
        M
      </span>
      <span aria-hidden="true" className="ml-[.07em] text-[.667em] tracking-[.035em]">
        ATE
      </span>
      <span aria-hidden="true" className="ml-[.035em] text-[1em] tracking-[.02em] text-brand">
        ERP
      </span>
    </span>
  );
}

/** Compact sidebar mark: "M" with a small cyan "ERP". */
export function CompactMark() {
  return (
    <span
      role="img"
      aria-label="MateERP"
      className="flex items-baseline font-wordmark leading-none"
    >
      <span aria-hidden="true" className="text-[24px] text-splash-fg">
        M
      </span>
      <span aria-hidden="true" className="ml-0.5 text-[10px] text-brand">
        ERP
      </span>
    </span>
  );
}
