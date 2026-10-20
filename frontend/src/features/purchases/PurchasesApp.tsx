'use client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { Gate } from '@/features/commerce/shared';
import { ModuleRoute } from '@/features/system/ModuleRoute';
import { OverviewPage, PurchaseHistory } from './Overview';
import { PayablesPage, PayableDetail } from './Payables';
import { VendorsPage, VendorDetail } from './Vendors';
import { VendorPaymentsPage, VendorPaymentDetail } from './Payments';
import { RecurringExpensesPage } from './Recurring';
export function PurchasesApp({ section, id }: { section: string; id?: string }) {
  const { can } = useAuth();
  if (section === 'orders') return <ModuleRoute itemId="purchases" group="Finance" subSlug="orders" />;
  return <Gate allow={can('finance.view')}>
    {section === 'overview' ? <OverviewPage /> : section === 'vendors' ? id ? <VendorDetail id={id} /> : <VendorsPage />
    : section === 'expenses' || section === 'bills' ? id ? <PayableDetail kind={section} id={id} /> : <PayablesPage kind={section} />
    : section === 'payments' ? id ? <VendorPaymentDetail id={id} /> : <VendorPaymentsPage /> : section === 'recurring' ? <RecurringExpensesPage /> : <PurchaseHistory />}
  </Gate>;
}
