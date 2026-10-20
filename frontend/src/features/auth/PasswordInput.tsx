'use client';

import { type InputHTMLAttributes, useState } from 'react';

import { Icon } from '@/components/ui/Icon';
import { cn } from '@/lib/cn';

interface PasswordInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  invalid?: boolean;
}

/** Password field with a show/hide control inside the 34px input frame. */
export function PasswordInput({ invalid, className, ...rest }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  return (
    <div
      className={cn(
        'flex h-[34px] w-full border bg-inp focus-within:border-ac',
        invalid ? 'border-err' : 'border-bd',
        className,
      )}
    >
      <input
        type={visible ? 'text' : 'password'}
        aria-invalid={invalid || undefined}
        className="min-w-0 flex-1 border-0 bg-transparent px-2.5 text-[13px] text-tx outline-none placeholder:text-tx3"
        {...rest}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
        className="flex w-9 flex-none items-center justify-center border-l border-bd bg-transparent text-tx3 hover:text-tx"
      >
        <Icon name={visible ? 'visibility_off' : 'visibility'} size={17} />
      </button>
    </div>
  );
}
