import { cn } from '@/lib/cn';

/** Square-cornered progress indicator. */
export function Spinner({ size = 16, className }: { size?: number; className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn('inline-block animate-spin border-2 border-bd2 border-t-ac', className)}
      style={{ width: size, height: size }}
    />
  );
}
