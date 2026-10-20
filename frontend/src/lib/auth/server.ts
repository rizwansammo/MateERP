import 'server-only';

import { cookies, headers } from 'next/headers';

import type { SessionInfo } from '@/lib/api/types';

const backendUrl = process.env.MATEERP_BACKEND_URL ?? 'http://127.0.0.1:8100';

/**
 * Resolve the current session on the server by forwarding the browser's
 * session cookie to Django. Used to protect pages before anything renders.
 * Returns null when the backend cannot be reached.
 */
export async function getServerSession(): Promise<SessionInfo | null> {
  const jar = await cookies();
  const session = jar.get('mateerp_session');
  if (!session) return { authenticated: false, user: null };
  try {
    const response = await fetch(`${backendUrl}/api/v1/auth/session/`, {
      headers: { Cookie: `mateerp_session=${session.value}`, Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!response.ok) return null;
    return (await response.json()) as SessionInfo;
  } catch {
    return null;
  }
}

/** The path the user requested (set by src/proxy.ts). */
export async function requestedPath(): Promise<string> {
  return (await headers()).get('x-mateerp-path') ?? '/dashboard';
}
