'use client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { Gate } from '@/features/commerce/shared';
import { PurchaseOrdersPage, PurchaseOrderDetail } from '@/features/operations/Procurement';
import { OnboardingPage } from '@/features/operations/Onboarding';
import { OverviewPage, PurchaseHistory } from './Overview';
import { PayablesPage, PayableDetail } from './Payables';
import { VendorsPage, VendorDetail } from './Vendors';
import { VendorPaymentsPage, VendorPaymentDetail } from './Payments';
import { RecurringExpensesPage } from './Recurring';
export function PurchasesApp({ section, id }: { section: string; id?: string }) {
  const { can } = useAuth();
  return <Gate allow={can('finance.view')}>
    {section === 'onboarding' ? <OnboardingPage /> : section === 'orders' ? id ? <PurchaseOrderDetail id={id} /> : <PurchaseOrdersPage /> : section === 'overview' ? <OverviewPage /> : section === 'vendors' ? id ? <VendorDetail id={id} /> : <VendorsPage />
    : section === 'expenses' || section === 'bills' ? id ? <PayableDetail kind={section} id={id} /> : <PayablesPage kind={section} />
    : section === 'payments' ? id ? <VendorPaymentDetail id={id} /> : <VendorPaymentsPage /> : section === 'recurring' ? <RecurringExpensesPage /> : <PurchaseHistory />}
  </Gate>;
}
