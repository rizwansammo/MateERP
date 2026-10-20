/**
 * Validate a post-login destination. Only same-origin application paths are
 * allowed, so a crafted ?next= link cannot send users to another site.
 */
export function safeNext(next: string | null | undefined, fallback = '/dashboard'): string {
  if (!next) return fallback;
  if (!next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return fallback;
  if (/[\u0000-\u001f]/.test(next)) return fallback;
  if (next.startsWith('/login') || next.startsWith('/api/')) return fallback;
  return next;
}

export function loginUrl(next?: string | null, reason?: 'expired'): string {
  const params = new URLSearchParams();
  const target = next ? safeNext(next, '') : '';
  if (target && target !== '/dashboard') params.set('next', target);
  if (reason) params.set('reason', reason);
  const qs = params.toString();
  return qs ? `/login?${qs}` : '/login';
}
