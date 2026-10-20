import type { Metadata, Viewport } from 'next';
import { Herr_Von_Muellerhoff, IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Serif } from 'next/font/google';
import localFont from 'next/font/local';
import type { ReactNode } from 'react';

import { BootSplash } from '@/components/brand/BootSplash';
import { PREFERENCES_BOOTSTRAP_SCRIPT } from '@/lib/preferences';

import '@/styles/globals.css';

// Fonts are self-hosted at build time: no runtime requests to third parties.
const plexSans = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-plex-sans',
  display: 'swap',
});

const plexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-plex-mono',
  display: 'swap',
});

// Document typography: serif option and the typed-signature script face.
const plexSerif = IBM_Plex_Serif({
  subsets: ['latin'],
  weight: ['400', '600', '700'],
  variable: '--font-plex-serif',
  display: 'swap',
});

const signature = Herr_Von_Muellerhoff({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-signature',
  display: 'swap',
});

const astro = localFont({
  src: '../assets/fonts/astro.ttf',
  variable: '--font-astro',
  display: 'block',
});

export const metadata: Metadata = {
  title: { default: 'MateERP', template: '%s · MateERP' },
  description: 'MateERP enterprise resource planning',
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: 'device-width', initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      data-theme="light"
      data-sidebar="full"
      suppressHydrationWarning
      className={`${plexSans.variable} ${plexMono.variable} ${plexSerif.variable} ${signature.variable} ${astro.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: PREFERENCES_BOOTSTRAP_SCRIPT }} />
        <noscript>
          <style>{'[data-testid="boot-splash"]{display:none!important}'}</style>
        </noscript>
      </head>
      <body>
        <BootSplash />
        {children}
      </body>
    </html>
  );
}
