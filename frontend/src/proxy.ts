import { type NextRequest, NextResponse } from 'next/server';

/*
 * First line of route protection: requests for application pages without a
 * session cookie go straight to the login screen. The (shell) layout then
 * validates the session with Django, and Django authorises every API call,
 * so this is a fast path, not the security boundary.
 */

const PUBLIC_PATHS = ['/login'];

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  if (!isPublic && !request.cookies.has('mateerp_session')) {
    const login = new URL('/login', request.url);
    const next = `${pathname}${search}`;
    if (next !== '/' && next !== '/dashboard') login.searchParams.set('next', next);
    return NextResponse.redirect(login);
  }

  const headers = new Headers(request.headers);
  headers.set('x-mateerp-path', `${pathname}${search}`);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  // Everything except the API proxy, Next.js internals and static files.
  matcher: ['/((?!api/|_next/|favicon\\.ico|.*\\.(?:png|jpg|jpeg|svg|webp|ico|txt|woff2?)$).*)'],
};
