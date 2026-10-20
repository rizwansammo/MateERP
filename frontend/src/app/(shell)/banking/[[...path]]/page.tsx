import { notFound } from 'next/navigation';

import { AccountingApp } from '@/features/accounting/AccountingApp';

const SECTIONS = ['overview', 'accounts', 'transactions', 'reconciliation', 'coa', 'ledger', 'journals', 'periods', 'tax', 'statements'];
export default async function BankingPage({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = ['overview'] } = await params;
  if (!SECTIONS.includes(path[0] ?? '') || path.length > 2) notFound();
  if (path[1] && (
    (path[0] === 'statements' && !['pnl', 'bs', 'cf', 'tb'].includes(path[1])) ||
    (['accounts', 'ledger'].includes(path[0]!) && !/^\d+$/.test(path[1])) ||
    (path[0] === 'journals' && !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(path[1])) ||
    !['statements', 'accounts', 'ledger', 'journals'].includes(path[0]!)
  )) notFound();
  return <AccountingApp section={path[0] ?? 'overview'} id={path[1]} />;
}
