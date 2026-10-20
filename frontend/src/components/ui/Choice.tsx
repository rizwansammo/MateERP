'use client';

import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

import { Icon } from './Icon';

interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
  id?: string;
}

/** Square checkbox (prototype: 16px box, primary fill when checked). */
export function Checkbox({ checked, onChange, label, hint, disabled, id }: CheckboxProps) {
  return (
    <div className="flex flex-col gap-1">
      <button
        id={id}
        type="button"
        role="checkbox"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className="flex items-start gap-2.5 bg-transparent py-0.5 text-left text-[13px] leading-[1.45] text-tx disabled:cursor-not-allowed disabled:opacity-60"
      >
        <span
          className={cn(
            'mt-px flex size-4 flex-none items-center justify-center border text-prt',
            checked ? 'border-pr bg-pr' : 'border-bd2 bg-inp',
          )}
        >
          {checked && <Icon name="check" size={14} className="font-semibold" />}
        </span>
        <span className="text-pretty">{label}</span>
      </button>
      {hint && <div className="pl-[26px] text-[11.5px] text-tx3">{hint}</div>}
    </div>
  );
}

interface SegmentedProps<T extends string> {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
  size?: 'md' | 'sm';
}

/** Segmented control (prototype seg fields and table filter chips). */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  size = 'md',
}: SegmentedProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="flex w-fit max-w-full flex-wrap border border-bd2">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              'whitespace-nowrap border-r border-bd font-medium last:border-r-0',
              size === 'md' ? 'h-8 px-3.5 text-[12.5px]' : 'h-[30px] px-[11px] text-[12px]',
              active ? 'bg-tx text-sf' : 'bg-transparent text-tx2 hover:bg-sf3',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

interface ToggleButtonProps {
  on: boolean;
  onToggle: () => void;
  disabled?: boolean;
  label: string;
}

/** On/Off toggle as used in the prototype's module list. */
export function ToggleButton({ on, onToggle, disabled, label }: ToggleButtonProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        'inline-flex h-[30px] items-center gap-[5px] border px-[11px] text-[12px] hover:brightness-[1.08]',
        'disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:brightness-100',
        on ? 'border-pr bg-pr font-semibold text-prt' : 'border-bd2 bg-sf font-medium text-tx',
      )}
    >
      <Icon name={on ? 'toggle_on' : 'toggle_off'} size={16} />
      {on ? 'On' : 'Off'}
    </button>
  );
}
