"use client";

import Link from "next/link";
import { useState } from "react";

import { Banner } from "@/components/ui/Banner";
import { Panel } from "@/components/ui/Panel";
import { StatGrid } from "@/components/ui/StatGrid";
import { Table, THead, TBody, TH, TR, TD } from "@/components/ui/Table";
import {
  Pager,
  SearchBox,
  TableState,
  TableToolbar,
} from "@/components/ui/TableKit";
import { errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useDebounced } from "@/lib/useDebounced";

import {
  DateFilters,
  JournalLink,
  QueryState,
  Screen,
  linkClass,
  useFinance,
  useRange,
  useMoney,
} from "./shared";
import type { Ledger, Report } from "./types";

const REPORTS = [
  { id: "pnl", title: "Profit & loss" },
  { id: "bs", title: "Balance sheet" },
  { id: "cf", title: "Cash movement" },
  { id: "tb", title: "Trial balance" },
];
export function StatementsPage({ which = "pnl" }: { which?: string }) {
  const amount = useMoney();
  const range = useRange();
  const { can } = useAuth();
  const query = useFinance<Report>(
    `/accounting/reports/${which}/?${range.query}`,
  );
  const data = query.data;
  const text = (k: string) =>
    typeof data?.[k] === "string"
      ? amount(data[k] as string, data.base_currency)
      : "—";
  const stats =
    which === "pnl"
      ? [
          { label: "Revenue", value: text("revenue") },
          { label: "Cost of sales", value: text("cost_of_sales") },
          { label: "Gross profit", value: text("gross_profit") },
          { label: "Expenses", value: text("expenses") },
          { label: "Net profit", value: text("net_profit") },
        ]
      : which === "bs"
        ? [
            { label: "Assets", value: text("assets") },
            { label: "Liabilities", value: text("liabilities") },
            { label: "Equity & earnings", value: text("equity") },
          ]
        : which === "cf"
          ? [
              { label: "Opening cash & bank", value: text("opening") },
              { label: "Receipts", value: text("receipts") },
              { label: "Payments", value: text("payments") },
              { label: "Internal transfers (excluded)", value: text("internal_transfers") },
              { label: "Transfer FX effect", value: text("transfer_fx_effect") },
              { label: "Closing cash & bank", value: text("closing") },
            ]
          : [
              { label: "Total debits", value: text("total_debits") },
              { label: "Total credits", value: text("total_credits") },
              { label: "Difference", value: text("difference") },
            ];
  return (
    <Screen
      eyebrow="Financial statements"
      title={
        REPORTS.find((r) => r.id === which)?.title ?? "Financial statement"
      }
      description="Derived from posted journals in the company base currency. Open account rows to inspect the underlying ledger."
      actions={
        <div className="flex flex-wrap gap-1">
          {REPORTS.map((r) => (
            <Link
              key={r.id}
              className={`inline-flex h-[34px] items-center border px-[11px] text-[12px] font-medium hover:no-underline ${r.id === which ? "border-pr bg-pr text-prt hover:text-prt" : "border-bd2 bg-sf text-tx hover:bg-sf3 hover:text-tx"}`}
              href={`/banking/statements/${r.id}`}
            >
              {r.title}
            </Link>
          ))}
        </div>
      }
    >
      <QueryState loading={query.loading} error={query.error} />
      {data && (
        <>
          {(which === "tb" || which === "bs") && (
            <Banner tone={data.balanced ? "ok" : "err"}>
              {data.balanced ? "Balanced" : "Out of balance"} · Difference{" "}
              {text("difference")}
              {which === 'tb' && <> · Debits {text('total_debits')} · Credits {text('total_credits')}</>}
            </Banner>
          )}
          {which === "cf" && (
            <Banner tone="info">
              Cash movement summary. Internal transfers are excluded from
              receipts and payments. Full statutory cash-flow classification is
              planned for Phase 6.
            </Banner>
          )}
          <Panel>
            <TableToolbar
              title={data.base_currency}
              subtitle={
                which === "tb" || which === "bs"
                  ? `As at ${range.to}`
                  : `${range.from} — ${range.to}`
              }
            >
              <DateFilters
                {...range}
                onFrom={range.setFrom}
                onTo={range.setTo}
              />
              {can("reports.export") && (
                <a
                  className={linkClass}
                  href={`/api/v1/accounting/reports/${which}/?${range.query}&export=csv`}
                >
                  Export CSV
                </a>
              )}
            </TableToolbar>
            <Table className="min-w-[750px] table-fixed [&_th:first-child]:w-[80px] [&_th:nth-child(3)]:w-[140px] [&_th:nth-child(n+4)]:w-[150px]">
              <THead>
                <TR>
                  <TH>Code</TH>
                  <TH>Account / line</TH>
                  <TH>Type / group</TH>
                  {which === "tb" ? (
                    <>
                      <TH align="right">Debit</TH>
                      <TH align="right">Credit</TH>
                    </>
                  ) : (
                    <TH align="right">Amount</TH>
                  )}
                </TR>
              </THead>
              <TBody>
                {data.rows.length === 0 && (
                  <TR>
                    <TD
                      colSpan={which === "tb" ? 5 : 4}
                      className="text-center text-tx3"
                    >
                      No posted activity for this report.
                    </TD>
                  </TR>
                )}
                {data.rows.map((r) => (
                  <TR
                    key={r.account_id}
                    className={r.is_summary ? "bg-sf2 font-semibold" : ""}
                  >
                    <TD className="font-mono">{r.code}</TD>
                    <TD>
                      <Link
                        href={`/banking/ledger/${r.account_id}?${range.query}`}
                      >
                        <span style={{ paddingLeft: (r.depth ?? 0) * 14 }}>
                          {r.name}
                          {r.is_summary ? " · subtotal" : ""}
                        </span>
                      </Link>
                    </TD>
                    <TD>{r.subtype || r.account_type}</TD>
                    {which === "tb" ? (
                      <>
                        <TD align="right">{amount(r.debit_balance)}</TD>
                        <TD align="right">{amount(r.credit_balance)}</TD>
                      </>
                    ) : (
                      <TD align="right">
                        {amount(
                          String(
                            r.report_amount ??
                              (which === "pnl" ? r.movement : r.balance),
                          ),
                        )}
                      </TD>
                    )}
                  </TR>
                ))}
                {which === "bs" && (
                  <>
                    <TR>
                      <TD />
                      <TD>Prior-year unclosed earnings</TD>
                      <TD>Equity</TD>
                      <TD align="right">{text("prior_earnings")}</TD>
                    </TR>
                    <TR>
                      <TD />
                      <TD>Current-year unclosed earnings</TD>
                      <TD>Equity</TD>
                      <TD align="right">{text("current_earnings")}</TD>
                    </TR>
                  </>
                )}
                {which !== "tb" &&
                  stats.slice(0, which === 'bs' ? stats.length : -1).map((s) => (
                    <TR key={s.label} className="bg-sf2 font-semibold">
                      <TD />
                      <TD>{s.label}</TD>
                      <TD />
                      <TD align="right">{s.value}</TD>
                    </TR>
                  ))}
                <TR className="bg-sf2 font-semibold">
                  <TD />
                  <TD>
                    {which === "pnl"
                      ? "Net profit / loss"
                      : which === "bs"
                        ? "Assets = liabilities + equity"
                        : which === "cf"
                          ? "Closing cash & bank"
                          : "Totals"}
                  </TD>
                  <TD />
                  {which === "tb" ? (
                    <>
                      <TD align="right">{text("total_debits")}</TD>
                      <TD align="right">{text("total_credits")}</TD>
                    </>
                  ) : (
                    <TD align="right">
                      {text(
                        which === "pnl"
                          ? "net_profit"
                          : which === "bs"
                            ? "assets"
                            : "closing",
                      )}
                    </TD>
                  )}
                </TR>
              </TBody>
            </Table>
          </Panel>
        </>
      )}
    </Screen>
  );
}

export function LedgerPage({ id }: { id?: string }) {
  return id ? <AccountLedger id={id} /> : <LedgerSummary />;
}
function LedgerSummary() {
  const amount = useMoney();
  const range = useRange();
  const query = useFinance<Report>(`/accounting/ledger/?${range.query}`);
  return (
    <Screen
      title="General ledger"
      description="Period activity by account. Open an account for its chronological ledger and running balances."
    >
      <DateFilters {...range} onFrom={range.setFrom} onTo={range.setTo} />
      <Panel>
        <Table>
          <THead>
            <TR>
              <TH>Code</TH>
              <TH>Account</TH>
              <TH align="right">Opening</TH>
              <TH align="right">Debits</TH>
              <TH align="right">Credits</TH>
              <TH align="right">Closing</TH>
            </TR>
          </THead>
          <TBody>
            <TableState
              loading={query.loading}
              colSpan={6}
              error={query.error ? errorMessage(query.error) : null}
              empty={
                query.data?.rows.length === 0
                  ? "No posted ledger activity."
                  : null
              }
            >
              {query.data?.rows.map((r) => (
                <TR key={r.account_id}>
                  <TD className="font-mono">{r.code}</TD>
                  <TD>
                    <Link
                      href={`/banking/ledger/${r.account_id}?${range.query}`}
                    >
                      {r.name}
                    </Link>
                  </TD>
                  <TD align="right">{amount(r.opening)}</TD>
                  <TD align="right">{amount(r.debit)}</TD>
                  <TD align="right">{amount(r.credit)}</TD>
                  <TD align="right" className="font-semibold">
                    {amount(r.balance)}
                  </TD>
                </TR>
              ))}
            </TableState>
          </TBody>
        </Table>
      </Panel>
    </Screen>
  );
}
function AccountLedger({ id }: { id: string }) {
  const amount = useMoney();
  const range = useRange();
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const q = useDebounced(search, 250);
  const query = useFinance<Ledger>(
    `/accounting/ledger/${id}/?${range.query}&page=${page}&search=${encodeURIComponent(q)}`,
  );
  const data = query.data;
  return (
    <Screen
      title={
        data ? `${data.account.code} · ${data.account.name}` : "Account ledger"
      }
      description="Posted entries with opening and closing balances. Search filters displayed lines; account totals and running balances retain the complete ledger."
      actions={
        <Link className={linkClass} href="/banking/coa">
          Chart of accounts
        </Link>
      }
    >
      <DateFilters {...range} onFrom={range.setFrom} onTo={range.setTo} />
      {data && (
        <StatGrid
          stats={[
            { label: "Opening", value: amount(data.opening), accentBar: true },
            { label: "Debits", value: amount(data.debit), accentBar: true },
            { label: "Credits", value: amount(data.credit), accentBar: true },
            { label: "Closing", value: amount(data.closing), accentBar: true },
          ]}
        />
      )}
      <Panel>
        <TableToolbar title="Ledger entries">
          <SearchBox
            value={search}
            onChange={(v) => {
              setSearch(v);
              setPage(1);
            }}
          />
          {can("reports.export") && (
            <a
              className={linkClass}
              href={`/api/v1/accounting/ledger/${id}/?${range.query}&search=${encodeURIComponent(q)}&export=csv`}
            >
              Export CSV
            </a>
          )}
        </TableToolbar>
        <Table>
          <THead>
            <TR>
              <TH>Date</TH>
              <TH>Reference</TH>
              <TH>Narration</TH>
              <TH align="right">Debit</TH>
              <TH align="right">Credit</TH>
              <TH align="right">Balance</TH>
            </TR>
          </THead>
          <TBody>
            <TableState
              colSpan={6}
              loading={query.loading}
              error={query.error ? errorMessage(query.error) : null}
              empty={data?.count === 0 ? "No entries." : null}
            >
              {data?.results.map((l) => (
                <TR key={l.id}>
                  <TD>{l.date}</TD>
                  <TD>
                    <JournalLink id={l.journal_id}>{l.number}</JournalLink>
                    <div className="text-[11.5px] text-tx3">{l.source}</div>
                  </TD>
                  <TD>{l.description}</TD>
                  <TD align="right">{amount(l.debit)}</TD>
                  <TD align="right">{amount(l.credit)}</TD>
                  <TD align="right" className="font-semibold">
                    {amount(l.balance)}
                  </TD>
                </TR>
              ))}
            </TableState>
          </TBody>
        </Table>
        {data && (
          <Pager
            page={page}
            totalPages={data.total_pages}
            pageSize={data.page_size}
            count={data.count}
            onPage={setPage}
          />
        )}
      </Panel>
    </Screen>
  );
}
