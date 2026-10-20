import type { ButtonHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

import { Icon } from './Icon';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'md' | 'sm';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: string;
}

const variants: Record<ButtonVariant, string> = {
  primary: 'border-pr bg-pr font-semibold text-prt',
  secondary: 'border-bd2 bg-sf font-medium text-tx',
  danger: 'border-err bg-transparent font-medium text-err',
  ghost: 'border-transparent bg-transparent font-medium text-tx2 hover:bg-sf3',
};

const sizes: Record<ButtonSize, string> = {
  md: 'h-[34px] gap-1.5 px-[14px] text-[12.5px]',
  sm: 'h-[30px] gap-[5px] px-[11px] text-[12px]',
};

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  type = 'button',
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      data-variant={variant}
      className={cn(
        'inline-flex shrink-0 items-center whitespace-nowrap border leading-none',
        'hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:brightness-100',
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {icon && <Icon name={icon} size={size === 'md' ? 17 : 16} />}
      {children}
    </button>
  );
}
