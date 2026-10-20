import type { Metadata } from 'next';

import { BrandingPage } from '@/features/settings/branding/BrandingPage';

export const metadata: Metadata = { title: 'Invoice & Receipt Branding' };

export default function Page() {
  return <BrandingPage />;
}
