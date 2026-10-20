'use client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { Gate } from '@/features/commerce/shared';
import { CustomersPage, CustomerDetail } from './Customers';
import { OverviewPage } from './Overview';
import { OrdersPage } from './Orders';
import { InvoicesPage, InvoiceDetail } from './Invoices';
import { InvoiceEditor } from './InvoiceEditor';
import { PaymentsPage, PaymentDetail } from './Payments';
import { CreditsPage } from './Credits';
import { ReceiptsPage, ReceiptDetail } from './Receipts';
import { ProjectsPage, ProjectDetail } from './Projects';
import { RecurringPage } from './Recurring';
import { SetupPage } from './Setup';

export function SalesApp({ section, id, edit = false }: { section: string; id?: string; edit?: boolean }) {
  const { can } = useAuth();
  return <Gate allow={can('finance.view')}>
    {section === 'overview' ? <OverviewPage /> : section === 'customers' ? id ? <CustomerDetail id={id} /> : <CustomersPage />
    : section === 'orders' ? <OrdersPage /> : section === 'invoices' ? id === 'new' || edit ? <Gate allow={can('invoices.create')} what="invoice creation"><InvoiceEditor id={id === 'new' ? undefined : id} /></Gate> : id ? <InvoiceDetail id={id} /> : <InvoicesPage />
    : section === 'payments' ? id ? <PaymentDetail id={id} /> : <PaymentsPage /> : section === 'receipts' ? id ? <ReceiptDetail id={id} /> : <ReceiptsPage />
    : section === 'projects' ? id ? <ProjectDetail id={id} /> : <ProjectsPage /> : section === 'recurring' ? <RecurringPage /> : section === 'setup' ? <SetupPage /> : <CreditsPage />}
  </Gate>;
}
