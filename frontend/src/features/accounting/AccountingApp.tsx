"use client";

import { AccountsPage } from "./Accounts";
import { BankAccountsPage, OverviewPage, TransactionsPage } from "./Banking";
import { JournalsPage } from "./Journals";
import { PeriodsPage, TaxPage } from "./PeriodsTaxFx";
import { ReconciliationPage } from "./Reconciliation";
import { LedgerPage, StatementsPage } from "./Reports";
import { FinancialGate } from "./shared";

export function AccountingApp({
  section,
  id,
}: {
  section: string;
  id?: string;
}) {
  return (
    <FinancialGate>
      {section === "overview" ? (
        <OverviewPage />
      ) : section === "coa" ? (
        <AccountsPage />
      ) : section === "journals" ? (
        <JournalsPage id={id} />
      ) : section === "ledger" ? (
        <LedgerPage id={id} />
      ) : section === "periods" ? (
        <PeriodsPage />
      ) : section === "tax" ? (
        <TaxPage />
      ) : section === "statements" ? (
        <StatementsPage which={id} />
      ) : section === "accounts" ? (
        <BankAccountsPage id={id} />
      ) : section === "transactions" ? (
        <TransactionsPage />
      ) : (
        <ReconciliationPage />
      )}
    </FinancialGate>
  );
}
