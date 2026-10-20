import type { NextConfig } from 'next';

// The browser only ever talks to this Next.js origin. API calls under /api/*
// are proxied to Django, so there is no CORS surface and session cookies stay
// first-party (needed for Phase 2 authentication and CSRF).
const backendUrl = process.env.MATEERP_BACKEND_URL ?? 'http://127.0.0.1:8100';

const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'same-origin' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Django URLs end in a slash; keep them intact through the proxy.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      { source: '/api/:path*/', destination: `${backendUrl}/api/:path*/` },
      { source: '/api/:path*', destination: `${backendUrl}/api/:path*` },
    ];
  },
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};

export default nextConfig;
