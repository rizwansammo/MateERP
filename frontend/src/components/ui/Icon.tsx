import { cn } from '@/lib/cn';

interface IconProps {
  /** Material Symbols Sharp ligature name, e.g. "space_dashboard". */
  name: string;
  size?: number;
  className?: string;
}

/** Decorative icon. Give the surrounding control an accessible label. */
export function Icon({ name, size = 18, className }: IconProps) {
  return (
    <span aria-hidden="true" className={cn('icon', className)} style={{ fontSize: size }}>
      {name}
    </span>
  );
}
