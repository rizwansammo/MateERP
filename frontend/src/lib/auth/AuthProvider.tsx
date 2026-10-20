'use client';

import { usePathname, useRouter } from 'next/navigation';
import { type ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { SESSION_EXPIRED_EVENT, api } from '@/lib/api/client';
import { resetQueries } from '@/lib/api/query';
import type { CurrentUser, Preferences } from '@/lib/api/types';
import { getSidebarMode, getTheme, setSidebarMode, setTheme } from '@/lib/preferences';

import { loginUrl } from './redirect';

interface AuthContextValue {
  user: CurrentUser;
  /** UX hint only — the server enforces every permission. */
  can: (code: string) => boolean;
  canAny: (...codes: string[]) => boolean;
  refresh: () => Promise<void>;
  setUser: (user: CurrentUser) => void;
  savePreferences: (prefs: Preferences) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>');
  return value;
}

export function AuthProvider({ initialUser, children }: { initialUser: CurrentUser; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState(initialUser);

  // Apply the account's saved theme and sidebar once per sign-in, so the
  // choice follows the user between browsers. The local copy stays the
  // pre-paint cache, which keeps first paint flash-free.
  useEffect(() => {
    const prefs = initialUser.preferences ?? {};
    if (prefs.theme && prefs.theme !== getTheme()) setTheme(prefs.theme);
    if (prefs.sidebar && prefs.sidebar !== getSidebarMode()) setSidebarMode(prefs.sidebar);
  }, [initialUser]);

  useEffect(() => {
    const onExpired = () => router.replace(loginUrl(window.location.pathname + window.location.search, 'expired'));
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [router]);

  const refresh = useCallback(async () => {
    setUser(await api.get<CurrentUser>('/auth/me/'));
  }, []);

  // Permissions can change at any time (an administrator edits a role);
  // re-read them whenever the user navigates so the UI does not lag behind.
  useEffect(() => {
    let active = true;
    api.get<CurrentUser>('/auth/me/').then(
      (fresh) => active && setUser(fresh),
      () => undefined,
    );
    return () => {
      active = false;
    };
  }, [pathname]);

  const savePreferences = useCallback((prefs: Preferences) => {
    void api
      .patch<CurrentUser>('/auth/me/', { preferences: prefs })
      .then(setUser)
      .catch(() => undefined);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.post('/auth/logout/');
    } finally {
      resetQueries();
      router.replace('/login');
      router.refresh();
    }
  }, [router]);

  const value = useMemo<AuthContextValue>(() => {
    const held = new Set(user.permissions);
    return {
      user,
      can: (code) => held.has(code),
      canAny: (...codes) => codes.some((c) => held.has(c)),
      refresh,
      setUser,
      savePreferences,
      signOut,
    };
  }, [user, refresh, savePreferences, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
