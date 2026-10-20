'use client';

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';

/*
 * Minimal shared query cache. Components reading the same key share one
 * request and one result; ``invalidate(prefix)`` refetches every mounted
 * query whose key starts with the prefix (e.g. after saving the company
 * profile, both the settings page and the sidebar card refresh).
 * The server stays the source of truth; nothing is persisted client-side.
 */

export interface QueryState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
}

interface Entry {
  state: QueryState<unknown>;
  listeners: Set<() => void>;
  fetcher?: () => Promise<unknown>;
  inflight?: Promise<void>;
  stale: boolean;
}

const EMPTY: QueryState<never> = { data: undefined, error: undefined, loading: true };
const entries = new Map<string, Entry>();

function entry(key: string): Entry {
  let found = entries.get(key);
  if (!found) {
    found = { state: EMPTY, listeners: new Set(), stale: true };
    entries.set(key, found);
  }
  return found;
}

function update(key: string, state: Partial<QueryState<unknown>>) {
  const e = entry(key);
  e.state = { ...e.state, ...state };
  e.listeners.forEach((listener) => listener());
}

function load(key: string, force = false): Promise<void> | undefined {
  const e = entry(key);
  if (!e.fetcher) return undefined;
  if (e.inflight) return e.inflight;
  if (!force && !e.stale) return undefined;
  if (!e.state.loading) update(key, { loading: true });
  const fetcher = e.fetcher;
  e.inflight = fetcher()
    .then(
      (data) => update(key, { data, error: undefined, loading: false }),
      (error: unknown) => update(key, { error, loading: false }),
    )
    .finally(() => {
      e.inflight = undefined;
      e.stale = false;
    });
  return e.inflight;
}

/** Mark matching queries stale and refetch those currently on screen. */
export function invalidate(prefix: string): void {
  for (const [key, e] of entries) {
    if (!key.startsWith(prefix)) continue;
    e.stale = true;
    if (e.listeners.size) void load(key, true);
  }
}

/** Replace cached data for a key (e.g. with a mutation's response). */
export function setQueryData<T>(key: string, data: T): void {
  entry(key).stale = false;
  update(key, { data, error: undefined, loading: false });
}

/** Clear everything (sign-out). */
export function resetQueries(): void {
  entries.clear();
}

export function useQuery<T>(key: string | null, fetcher: () => Promise<T>) {
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const subscribe = useCallback(
    (listener: () => void) => {
      if (!key) return () => {};
      const e = entry(key);
      e.listeners.add(listener);
      return () => {
        e.listeners.delete(listener);
      };
    },
    [key],
  );
  const state = useSyncExternalStore(
    subscribe,
    () => (key ? (entry(key).state as QueryState<T>) : (EMPTY as QueryState<T>)),
    () => EMPTY as QueryState<T>,
  );

  useEffect(() => {
    if (!key) return;
    entry(key).fetcher = () => fetcherRef.current();
    void load(key);
  }, [key]);

  const refresh = useCallback(() => (key ? load(key, true) : undefined), [key]);
  const mutate = useCallback((data: T) => key && setQueryData(key, data), [key]);
  return { ...state, refresh, mutate };
}
