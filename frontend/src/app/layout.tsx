import type { Metadata, Viewport } from 'next';
import localFont from 'next/font/local';
import type { ReactNode } from 'react';

import { BootSplash } from '@/components/brand/BootSplash';
import { PREFERENCES_BOOTSTRAP_SCRIPT } from '@/lib/preferences';

import '@/styles/globals.css';

// Reproducible, bundled open-source IBM Plex font faces; never fetch from
// Google Fonts during builds or from third parties in the browser.
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-sans/700.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import '@fontsource/ibm-plex-mono/600.css';
import '@fontsource/ibm-plex-serif/400.css';
import '@fontsource/ibm-plex-serif/600.css';
import '@fontsource/ibm-plex-serif/700.css';
import '@fontsource/herr-von-muellerhoff/400.css';

const optimus = localFont({
  src: '../assets/fonts/optimus.woff2',
  variable: '--font-optimus',
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
      className={`${optimus.variable}`}
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
