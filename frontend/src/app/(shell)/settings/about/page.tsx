import type { Metadata } from 'next';

import { AboutPage } from '@/features/settings/other/OtherPages';

export const metadata: Metadata = { title: 'About MateERP' };

export default function Page() {
  return <AboutPage />;
}
