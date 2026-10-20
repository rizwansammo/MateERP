'use client';

import { useSyncExternalStore } from 'react';

/*
 * Per-browser UI preferences (theme and sidebar width).
 *
 * The source of truth is an attribute on <html>, set before first paint by
 * PREFERENCES_BOOTSTRAP_SCRIPT, so CSS renders the right theme and sidebar
 * width without a flash. These hooks only mirror that attribute for React.
 */

export type Theme = 'light' | 'dark';
export type SidebarMode = 'full' | 'compact';

export const THEME_STORAGE_KEY = 'mateerp.theme';
export const SIDEBAR_STORAGE_KEY = 'mateerp.sidebar';

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function persist(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage can be unavailable (private mode, policy); the preference then
    // lasts for this page only.
  }
}

export function getTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  persist(THEME_STORAGE_KEY, theme);
  listeners.forEach((listener) => listener());
}

export function getSidebarMode(): SidebarMode {
  return document.documentElement.dataset.sidebar === 'compact' ? 'compact' : 'full';
}

export function setSidebarMode(mode: SidebarMode): void {
  document.documentElement.dataset.sidebar = mode;
  persist(SIDEBAR_STORAGE_KEY, mode);
  listeners.forEach((listener) => listener());
}

export function useTheme() {
  const theme = useSyncExternalStore<Theme>(subscribe, getTheme, () => 'light');
  return {
    theme,
    setTheme,
    toggleTheme: () => setTheme(theme === 'dark' ? 'light' : 'dark'),
  };
}

export function useSidebarMode() {
  const mode = useSyncExternalStore<SidebarMode>(subscribe, getSidebarMode, () => 'full');
  return {
    mode,
    setMode: setSidebarMode,
    toggle: () => setSidebarMode(mode === 'compact' ? 'full' : 'compact'),
  };
}

/** Runs in <head> before paint; must stay dependency-free. */
export const PREFERENCES_BOOTSTRAP_SCRIPT = `try{var d=document.documentElement,t=localStorage.getItem('${THEME_STORAGE_KEY}'),s=localStorage.getItem('${SIDEBAR_STORAGE_KEY}');d.dataset.theme=t==='dark'?'dark':'light';d.dataset.sidebar=s==='compact'?'compact':'full'}catch(e){}`;
