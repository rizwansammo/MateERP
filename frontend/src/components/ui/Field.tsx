import type { ReactNode } from 'react';

interface FieldProps {
  label: string;
  htmlFor: string;
  required?: boolean;
  hint?: string;
  error?: string;
  children: ReactNode;
}

/** Label + control + hint/error, laid out like the prototype's form drawer. */
export function Field({ label, htmlFor, required, hint, error, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-[11.5px] font-medium text-tx2">
        {label}
        {required && <span aria-hidden="true" className="text-err"> *</span>}
      </label>
      {children}
      {error ? (
        <span id={`${htmlFor}-error`} role="alert" className="text-[11.5px] text-err">
          {error}
        </span>
      ) : (
        hint && (
          <span id={`${htmlFor}-hint`} className="text-[11.5px] text-tx3">
            {hint}
          </span>
        )
      )}
    </div>
  );
}
