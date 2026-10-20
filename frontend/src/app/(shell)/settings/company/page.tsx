import type { Metadata } from 'next';

import { CompanyPage } from '@/features/settings/company/CompanyPage';

export const metadata: Metadata = { title: 'Company Profile' };

export default function Page() {
  return <CompanyPage />;
}
