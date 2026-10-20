import type { ButtonHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

import { Icon } from './Icon';

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> {
  icon: string;
  /** Required: icon-only controls must have an accessible name. */
  label: string;
  iconSize?: number;
}

/** 34px square header-style control. */
export function IconButton({
  icon,
  label,
  iconSize = 19,
  type = 'button',
  className,
  children,
  ...rest
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={rest.title ?? label}
      className={cn(
        'relative flex size-[34px] shrink-0 items-center justify-center border border-bd bg-transparent text-tx',
        'hover:bg-sf3 disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:bg-transparent',
        className,
      )}
      {...rest}
    >
      <Icon name={icon} size={iconSize} />
      {children}
    </button>
  );
}
