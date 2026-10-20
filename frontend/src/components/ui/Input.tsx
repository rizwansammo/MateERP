import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

const control =
  'w-full min-w-0 border bg-inp text-tx outline-none placeholder:text-tx3 focus:border-ac disabled:cursor-not-allowed disabled:opacity-60';

const border = (invalid?: boolean) => (invalid ? 'border-err' : 'border-bd');

interface InvalidProp {
  invalid?: boolean;
  /** sm: 30px toolbar control. */
  controlSize?: 'md' | 'sm';
}

const height = (size?: 'md' | 'sm') => (size === 'sm' ? 'h-[30px] text-[12.5px]' : 'h-[34px]');

export function Input({
  invalid,
  controlSize: size,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & InvalidProp) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={cn(control, height(size), size === 'sm' ? '' : 'text-[13px]', 'px-2.5', border(invalid), className)}
      {...rest}
    />
  );
}

/** Right-aligned tabular input for amounts. Values stay strings; never parse money as float. */
export function AmountInput({
  invalid,
  controlSize: size,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & InvalidProp) {
  return (
    <input
      inputMode="decimal"
      aria-invalid={invalid || undefined}
      className={cn(
        control,
        height(size),
        'px-2.5 text-right font-medium tabular-nums',
        border(invalid),
        className,
      )}
      {...rest}
    />
  );
}

export function Select({
  invalid,
  controlSize: size,
  className,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & InvalidProp) {
  return (
    <select
      aria-invalid={invalid || undefined}
      className={cn(
        control,
        height(size),
        size === 'sm' ? '' : 'text-[13px]',
        'appearance-none bg-[image:var(--chev)] bg-[position:right_10px_center] bg-no-repeat pl-2.5 pr-7',
        border(invalid),
        className,
      )}
      {...rest}
    >
      {children}
    </select>
  );
}

export function Textarea({
  invalid,
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  return (
    <textarea
      aria-invalid={invalid || undefined}
      className={cn(control, 'resize-y px-2.5 py-2 text-[13px] leading-normal', border(invalid), className)}
      {...rest}
    />
  );
}
