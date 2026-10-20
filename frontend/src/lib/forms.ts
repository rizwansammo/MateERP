'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { ApiError } from './api/client';

/** Form values with dirty tracking against the last saved state. */
export function useFormState<T extends Record<string, unknown>>(initial: T) {
  const [saved, setSaved] = useState(initial);
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const dirty = useMemo(() => JSON.stringify(values) !== JSON.stringify(saved), [values, saved]);

  const set = useCallback(<K extends keyof T>(key: K, value: T[K]) => {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => {
      if (!(key as string in e)) return e;
      const next = { ...e };
      delete next[key as string];
      return next;
    });
  }, []);

  /** Replace both saved and current values (e.g. after loading or saving). */
  const reset = useCallback((next: T) => {
    setSaved(next);
    setValues(next);
    setErrors({});
  }, []);

  /** Show API validation errors next to fields; returns a general message, if any. */
  const applyError = useCallback((error: unknown): string | null => {
    if (error instanceof ApiError && error.code === 'validation_error') {
      const fields = error.fieldErrors();
      setErrors(fields);
      return fields.non_field_errors ?? (Object.keys(fields).length ? 'Check the highlighted fields.' : error.message);
    }
    return error instanceof Error ? error.message : 'Saving failed.';
  }, []);

  return { values, set, setValues, errors, setErrors, dirty, reset, applyError };
}

/** Warn before the tab is closed or reloaded with unsaved changes. */
export function useUnsavedGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);
}
