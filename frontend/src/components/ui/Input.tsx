import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

const control =
  'w-full min-w-0 border bg-inp text-[13px] text-tx outline-none placeholder:text-tx3 focus:border-ac disabled:cursor-not-allowed disabled:opacity-60';

const border = (invalid?: boolean) => (invalid ? 'border-err' : 'border-bd');

interface InvalidProp {
  invalid?: boolean;
}

export function Input({
  invalid,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & InvalidProp) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={cn(control, 'h-[34px] px-2.5', border(invalid), className)}
      {...rest}
    />
  );
}

/** Right-aligned tabular input for amounts. Values stay strings; never parse money as float. */
export function AmountInput({
  invalid,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & InvalidProp) {
  return (
    <input
      inputMode="decimal"
      aria-invalid={invalid || undefined}
      className={cn(
        control,
        'h-[34px] px-2.5 text-right font-medium tabular-nums',
        border(invalid),
        className,
      )}
      {...rest}
    />
  );
}

export function Select({
  invalid,
  className,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & InvalidProp) {
  return (
    <select
      aria-invalid={invalid || undefined}
      className={cn(
        control,
        'h-[34px] appearance-none bg-[image:var(--chev)] bg-[position:right_10px_center] bg-no-repeat pl-2.5 pr-7',
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
}: TextareaHTMLAttributes<HTMLTextAreaElement> & InvalidProp) {
  return (
    <textarea
      aria-invalid={invalid || undefined}
      className={cn(control, 'resize-y px-2.5 py-2 leading-normal', border(invalid), className)}
      {...rest}
    />
  );
}
