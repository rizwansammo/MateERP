"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/Panel";
import { StatGrid } from "@/components/ui/StatGrid";
import { Table, THead, TBody, TH, TR, TD } from "@/components/ui/Table";
import {
  Pager,
  SearchBox,
  TableState,
  TableToolbar,
} from "@/components/ui/TableKit";
import { api, errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useDebounced } from "@/lib/useDebounced";

import { decimal, minor } from "./money";
import {
  DateFilters,
  EntityDrawer,
  type FormField,
  JournalLink,
  type Page,
  QueryState,
  Screen,
  key,
  linkClass,
  today,
  useAccounts,
  useConfig,
  useFinance,
  useRange,
  useMoney,
} from "./shared";
import type { Bank, BankLine, Journal, Line } from "./types";

export function BankAccountsPage({ id }: { id?: string }) {
  const amount = useMoney();
  const { can } = useAuth();
  const banks = useFinance<Page<Bank>>("/banking/accounts/?page_size=100");
  const accounts = useAccounts();
  const config = useConfig();
  const detail = useFinance<Bank | null>(
    id ? `/banking/accounts/${id}/` : null,
  );
  const [edit, setEdit] = useState<Bank | "new" | null>(null);
  const [tx, setTx] = useState(false);
  const selected = id ? detail.data : undefined;
  const fields: FormField[] = [
    { key: "name", label: "Account name", required: true },
    {
      key: "kind",
      label: "Type",
      options: [
        { value: "bank", label: "Bank account" },
        { value: "cash", label: "Cash account" },
      ],
    },
    { key: "institution", label: "Bank / institution" },
    { key: "identifier", label: "Account identifier (optional)" },
    {
      key: "currency",
      label: "Currency",
      options: (config.data?.enabled_currencies ?? []).map((c) => ({
        value: c,
        label: c,
      })),
    },
    {
      key: "gl_account_id",
      label: "Linked GL account",
      type: "id",
      options: [
        { value: "", label: "Select account" },
        ...(accounts.data ?? [])
          .filter(
            (a) => a.account_type === "asset" && a.is_postable && a.is_active,
          )
          .map((a) => ({
            value: String(a.id),
            label: `${a.code} · ${a.name}`,
          })),
      ],
    },
    { key: "is_active", label: "Active", type: "checkbox" },
  ];
  return (
    <Screen
      title={selected?.name ?? "Bank & cash accounts"}
      description="Every account holding company money. Balances are derived solely from posted journal entries."
      actions={
        can("accounting.manage") && (
          <>
            <Button icon="swap_horiz" onClick={() => setTx(true)}>
              Transfer / transaction
            </Button>
            <Button
              variant="primary"
              icon="add"
              disabled={!config.data?.base_currency}
              onClick={() => setEdit(selected ?? "new")}
            >
              {selected ? "Edit account" : "New bank account"}
            </Button>
          </>
        )
      }
    >
      <QueryState loading={config.loading} error={config.error} />
      {selected ? (
        <>
          <StatGrid
            stats={[
              { label: "Currency", value: selected.currency, accentBar: true },
              {
                label: "Ledger balance",
                value: amount(selected.balance, selected.currency),
                accentBar: true,
              },
              {
                label: "Base book value",
                value: amount(selected.book_value, config.data?.base_currency),
                accentBar: true,
              },
            ]}
          />
          <Banner tone="info">
            {selected.institution} · {selected.identifier || "No identifier"} ·{" "}
            <Link href={`/banking/ledger/${selected.gl_account_id}`}>
              Open general ledger
            </Link>
          </Banner>
          <TransactionsTable bankId={selected.id} />
        </>
      ) : (
        <Panel>
          <Table>
            <THead>
              <TR>
                <TH>Account</TH>
                <TH>Type</TH>
                <TH>Institution / number</TH>
                <TH>Ccy</TH>
                <TH>GL</TH>
                <TH align="right">Balance</TH>
                <TH align="right">Book value</TH>
                <TH>Actions</TH>
              </TR>
            </THead>
            <TBody>
              <TableState
                colSpan={8}
                loading={banks.loading}
                error={banks.error ? errorMessage(banks.error) : null}
                empty={
                  banks.data?.count === 0
                    ? "No bank or cash accounts yet. Create an account and link it to a posting asset in the chart."
                    : null
                }
              >
                {banks.data?.results.map((b) => (
                  <TR key={b.id}>
                    <TD>
                      <Link href={`/banking/accounts/${b.id}`}>{b.name}</Link>
                      {!b.is_active && <Badge tone="neutral">Inactive</Badge>}
                    </TD>
                    <TD>{b.kind}</TD>
                    <TD>
                      {b.institution}
                      <div className="text-[11.5px] text-tx3">
                        {b.identifier}
                      </div>
                    </TD>
                    <TD className="font-mono">{b.currency}</TD>
                    <TD>
                      <Link href={`/banking/ledger/${b.gl_account_id}`}>
                        {accounts.data?.find((a) => a.id === b.gl_account_id)
                          ?.code ?? b.gl_account_id}
                      </Link>
                    </TD>
                    <TD align="right">{amount(b.balance, b.currency)}</TD>
                    <TD align="right">
                      {amount(b.book_value, config.data?.base_currency)}
                    </TD>
                    <TD>
                      {can("accounting.manage") && (
                        <Button size="xs" onClick={() => setEdit(b)}>
                          Edit
                        </Button>
                      )}
                    </TD>
                  </TR>
                ))}
              </TableState>
            </TBody>
          </Table>
        </Panel>
      )}
      {id && <QueryState loading={detail.loading} error={detail.error} />}
      {edit && (
        <EntityDrawer
          title={
            edit === "new" ? "New bank or cash account" : `Edit ${edit.name}`
          }
          fields={fields}
          initial={
            edit === "new"
              ? {
                  name: "",
                  kind: "bank",
                  institution: "",
                  identifier: "",
                  currency: config.data?.base_currency ?? "",
                  gl_account_id: "",
                  is_active: true,
                }
              : {
                  name: edit.name,
                  kind: edit.kind,
                  institution: edit.institution,
                  identifier: "",
                  currency: edit.currency,
                  gl_account_id: String(edit.gl_account_id),
                  is_active: edit.is_active,
                }
          }
          onClose={() => setEdit(null)}
          onSave={(data) => {
            if (edit !== "new" && !data.identifier) delete data.identifier;
            return edit === "new"
              ? api.post("/banking/accounts/", data)
              : api.patch(`/banking/accounts/${edit.id}/`, data);
          }}
        >
          <p className="text-[12px] text-tx3 mt-4">
            Opening balances are entered through Journals → Opening balances.
            The GL account must be an active posting asset.
          </p>
        </EntityDrawer>
      )}
      {tx && (
        <TransactionDrawer
          banks={banks.data?.results ?? []}
          onClose={() => setTx(false)}
        />
      )}
    </Screen>
  );
}

export function TransactionsPage() {
  const { can } = useAuth();
  const [edit, setEdit] = useState(false);
  const banks = useFinance<Page<Bank>>("/banking/accounts/?page_size=100");
  return (
    <Screen
      title="Transactions"
      description="Posted movements across bank and cash accounts. Ledger transfers record movements; they do not send instructions to a bank."
      actions={
        can("accounting.manage") && (
          <Button variant="primary" icon="add" onClick={() => setEdit(true)}>
            Record transaction
          </Button>
        )
      }
    >
      <TransactionsTable />
      {edit && (
        <TransactionDrawer
          banks={banks.data?.results ?? []}
          onClose={() => setEdit(false)}
        />
      )}
    </Screen>
  );
}
export function TransactionsTable({
  bankId,
  recent = false,
}: {
  bankId?: number;
  recent?: boolean;
}) {
  const amount = useMoney();
  const range = useRange();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const q = useDebounced(search, 250);
  const banks = useFinance<Page<Bank>>("/banking/accounts/?page_size=100");
  const [bank, setBank] = useState(bankId ? String(bankId) : "");
  const effectiveBank = bankId ? String(bankId) : bank;
  const query = useFinance<Page<BankLine>>(
    recent
      ? "/banking/transactions/?page_size=12"
      : `/banking/transactions/?${range.query}&bank=${effectiveBank}&search=${encodeURIComponent(q)}&page=${page}`,
  );
  return (
    <Panel>
      <TableToolbar
        title={
          recent ? "Recent bank & cash movements" : "Bank & cash movements"
        }
      >
        {recent ? (
          <Link className={linkClass} href="/banking/transactions">
            All transactions
          </Link>
        ) : (
          <>
            <span className="w-[160px]">
              <Select
                controlSize="sm"
                aria-label="Filter bank account"
                value={effectiveBank}
                disabled={!!bankId}
                onChange={(e) => {
                  setBank(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All accounts</option>
                {banks.data?.results.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            </span>
            <SearchBox
              value={search}
              onChange={(v) => {
                setSearch(v);
                setPage(1);
              }}
            />
          </>
        )}
      </TableToolbar>
      {!recent && (
        <div className="p-3.5">
          <DateFilters {...range} onFrom={range.setFrom} onTo={range.setTo} />
        </div>
      )}
      <Table>
        <THead>
          <TR>
            <TH>Date</TH>
            <TH>Reference</TH>
            <TH>Description</TH>
            <TH align="right">Money in</TH>
            <TH align="right">Money out</TH>
            <TH>Bank match</TH>
          </TR>
        </THead>
        <TBody>
          <TableState
            colSpan={6}
            loading={query.loading}
            error={query.error ? errorMessage(query.error) : null}
            empty={
              query.data?.count === 0
                ? "No posted bank or cash movements."
                : null
            }
          >
            {query.data?.results.map((l) => (
              <TR key={l.id}>
                <TD>{l.date}</TD>
                <TD>
                  <JournalLink id={l.journal_id}>{l.number}</JournalLink>
                  <div className="text-[11.5px] text-tx3">{l.source}</div>
                </TD>
                <TD>{l.description || l.account_name}</TD>
                <TD align="right" className="text-ok">
                  {minor(l.debit) ? amount(l.debit, l.currency) : "—"}
                </TD>
                <TD align="right">
                  {minor(l.credit) ? amount(l.credit, l.currency) : "—"}
                </TD>
                <TD>
                  <Badge tone={l.matched ? "ok" : "warn"}>
                    {l.matched ? "Reconciled" : "Unreconciled"}
                  </Badge>
                </TD>
              </TR>
            ))}
          </TableState>
        </TBody>
      </Table>
      {query.data && !recent && (
        <Pager
          page={page}
          totalPages={query.data.total_pages}
          count={query.data.count}
          pageSize={query.data.page_size}
          onPage={setPage}
        />
      )}
    </Panel>
  );
}

interface Quote {
  quote_fingerprint: string;
  lines: Line[];
  fx_difference: string;
  fx_account: string | null;
  base_currency: string;
}
export function TransactionDrawer({
  banks,
  onClose,
  initial,
}: {
  banks: Bank[];
  onClose: () => void;
  initial?: Record<string, string>;
}) {
  const amount = useMoney();
  const accounts = useAccounts();
  const [preview, setPreview] = useState<{
    input: string;
    quote: Quote;
  } | null>(null);
  const postingKey = useRef(key());
  const opts = [
    { value: "", label: "Select account" },
    ...banks
      .filter((b) => b.is_active)
      .map((b) => ({
        value: String(b.id),
        label: `${b.name} (${b.currency})`,
      })),
  ];
  const fields: FormField[] = [
    {
      key: "kind",
      label: "Transaction type",
      options: [
        { value: "transfer", label: "Internal transfer" },
        { value: "deposit", label: "Money in / deposit" },
        { value: "withdrawal", label: "Money out / withdrawal" },
        { value: "charge", label: "Bank charge" },
        { value: "interest", label: "Interest income" },
        { value: "adjustment_in", label: "Manual adjustment in" },
        { value: "adjustment_out", label: "Manual adjustment out" },
      ],
    },
    {
      key: "bank_account_id",
      label: "From / primary account",
      type: "id",
      options: opts,
    },
    { key: "posting_date", label: "Posting date", type: "date" },
    {
      key: "amount",
      label: "Amount (primary account currency)",
      type: "amount",
    },
    {
      key: "destination_id",
      label: "Destination (transfers)",
      type: "id",
      options: opts,
    },
    {
      key: "received_amount",
      label: "Received amount (cross-currency transfers)",
      type: "amount",
      hint: "Required when currencies differ; ignored for same-currency transfers.",
    },
    {
      key: "counter_account_id",
      label: "Offset account (non-transfers)",
      type: "id",
      options: [
        { value: "", label: "Select offset account" },
        ...(accounts.data ?? [])
          .filter(
            (a) =>
              a.is_active &&
              a.is_postable &&
              !banks.some((b) => b.gl_account_id === a.id),
          )
          .map((a) => ({
            value: String(a.id),
            label: `${a.code} · ${a.name}`,
          })),
      ],
    },
    { key: "description", label: "Description", required: true },
    { key: "reason", label: "Reason / reference", type: "textarea" },
  ];
  return (
    <EntityDrawer
      title="Record bank transaction"
      width={600}
      fields={fields}
      saveLabel={preview ? "Confirm & post" : "Preview transaction"}
      initial={{
        kind: "transfer",
        bank_account_id: banks[0] ? String(banks[0].id) : "",
        destination_id: "",
        counter_account_id: "",
        posting_date: today(),
        amount: "",
        received_amount: "",
        description: "",
        reason: "",
        ...initial,
      }}
      onClose={onClose}
      onSave={async (data) => {
        const payload: Record<string, unknown> = {
          ...data,
          posting_key: postingKey.current,
        };
        if (!payload.received_amount) delete payload.received_amount;
        if (!payload.destination_id) delete payload.destination_id;
        if (!payload.counter_account_id) delete payload.counter_account_id;
        const serialized = JSON.stringify(payload);
        if (!preview || preview.input !== serialized) {
          const quote = await api.post<Quote>(
            "/banking/transactions/preview/",
            payload,
          );
          setPreview({ input: serialized, quote });
          return false;
        }
        const result = await api.post<Journal>("/banking/transactions/", {
          ...payload,
          confirm_fx: true,
          quote_fingerprint: preview.quote.quote_fingerprint,
        });
        if (result.status === "pending") return result;
        return result;
      }}
    >
      <div className="mt-4 flex flex-col gap-3">
        <Banner tone="info">
          Review the balanced ledger entry before confirming. Financial
          adjustment approval policies are enforced when applicable.
        </Banner>
        {preview && (
          <>
            <Banner tone={minor(preview.quote.fx_difference) ? "warn" : "ok"}>
              Preview ready. FX difference:{" "}
              {amount(preview.quote.fx_difference, preview.quote.base_currency)}{" "}
              {preview.quote.fx_account && `· ${preview.quote.fx_account}`}
            </Banner>
            <Table>
              <THead>
                <TR>
                  <TH>Account</TH>
                  <TH align="right">Debit (base)</TH>
                  <TH align="right">Credit (base)</TH>
                </TR>
              </THead>
              <TBody>
                {preview.quote.lines.map((l, i) => (
                  <TR key={i}>
                    <TD>
                      {accounts.data?.find((a) => a.id === l.account_id)
                        ?.name ?? l.account_id}
                    </TD>
                    <TD align="right">{amount(l.base_debit)}</TD>
                    <TD align="right">{amount(l.base_credit)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </>
        )}
      </div>
    </EntityDrawer>
  );
}

interface Overview {
  accounts: Bank[];
  cash_movement: {
    opening: string;
    closing: string;
    receipts: string;
    payments: string;
  };
  trial_balance: { balanced: boolean; total: string };
  open_periods: number;
  unmatched_statement: number;
  months: {
    month: string;
    balance: string;
    accounts: Record<string, string>;
  }[];
}
export function OverviewPage() {
  const amount = useMoney();
  const { can } = useAuth();
  const query = useFinance<Overview>("/banking/overview/");
  const [tx, setTx] = useState(false);
  const data = query.data;
  const values =
    data?.months.flatMap((m) =>
      Object.values(m.accounts).map((v) => minor(v)),
    ) ?? [];
  const lo = values.reduce((m, v) => (v < m ? v : m), 0n);
  const hi = values.reduce((m, v) => (v > m ? v : m), 0n);
  const span = hi - lo || 1000000n;
  // Only the bounded SVG coordinate is converted to Number; balances stay exact.
  const y = (v: bigint) => 195 - Number(((v - lo) * 180n) / span);
  const x = (i: number) =>
    55 + (i * 420) / Math.max(1, (data?.months.length ?? 1) - 1);
  return (
    <Screen
      title="Banking & accounting overview"
      description="Cash position, ledger health and period status from posted accounting data. Transfers record company money movements; they do not send instructions to a bank."
      actions={
        can("accounting.manage") && (
          <div className="flex gap-2">
            <Button icon="swap_horiz" onClick={() => setTx(true)}>
              Transfer
            </Button>
            <Button variant="primary" icon="add" onClick={() => setTx(true)}>
              Record transaction
            </Button>
          </div>
        )
      }
    >
      <QueryState loading={query.loading} error={query.error} />
      {data && (
        <>
          <StatGrid
            minWidth={180}
            stats={[
              {
                label: "Total cash & bank",
                value: amount(data.cash_movement.closing),
                sub: `${data.accounts.length} accounts · base book value`,
                accentBar: true,
              },
              {
                label: "Money in · this month",
                value: amount(data.cash_movement.receipts),
                accentBar: true,
              },
              {
                label: "Money out · this month",
                value: amount(data.cash_movement.payments),
                accentBar: true,
              },
              {
                label: "Unmatched statement lines",
                value: String(data.unmatched_statement),
                tone: data.unmatched_statement ? "warn" : "ok",
              },
              {
                label: "Trial balance",
                value: data.trial_balance.balanced
                  ? "Balanced"
                  : "Out of balance",
                tone: data.trial_balance.balanced ? "ok" : "err",
              },
              {
                label: "Open periods",
                value: String(data.open_periods),
                accentBar: true,
              },
            ]}
          />
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,440px),1fr))] gap-[18px]">
            <Panel>
              <PanelHeader
                title="Month-end cash balance"
                subtitle="All cash and bank accounts · base book value"
              />
              <PanelBody>
                <div className="mb-3 flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-tx2">
                  {data.accounts.map((b, i) => (
                    <span key={b.id} className="flex items-center gap-1.5">
                      <span
                        className="h-px w-2.5"
                        style={{ background: `var(--c${(i % 6) + 1})` }}
                      />
                      {b.name}
                    </span>
                  ))}
                </div>
                <svg
                  role="img"
                  aria-label="Month-end cash balance chart"
                  viewBox="0 0 500 230"
                  className="h-[230px] w-full"
                >
                  {[15, 60, 105, 150, 195].map((tick) => (
                    <path
                      key={tick}
                      d={`M55 ${tick} H475`}
                      fill="none"
                      stroke="var(--bd)"
                      strokeDasharray="2 3"
                    />
                  ))}
                  {data.accounts.map((b, i) => {
                    const pts = data.months
                      .map(
                        (m, n) =>
                          `${x(n)},${y(minor(m.accounts[b.id] ?? "0"))}`,
                      )
                      .join(" ");
                    const color = `var(--c${(i % 6) + 1})`;
                    return (
                      <g key={b.id}>
                        <polygon
                          points={`55,${y(0n)} ${pts} 475,${y(0n)}`}
                          fill={color}
                          fillOpacity=".1"
                        />
                        <polyline
                          fill="none"
                          stroke={color}
                          strokeWidth="1.8"
                          points={pts}
                        />
                        {data.months.map((m, n) => (
                          <rect
                            key={m.month}
                            x={x(n) - 2}
                            y={y(minor(m.accounts[b.id] ?? "0")) - 2}
                            width="4"
                            height="4"
                            fill="var(--sf)"
                            stroke={color}
                          >
                            <title>
                              {b.name} · {m.month} · {amount(m.accounts[b.id])}
                            </title>
                          </rect>
                        ))}
                      </g>
                    );
                  })}
                  <text
                    x="50"
                    y="18"
                    textAnchor="end"
                    fontSize="9"
                    fill="var(--tx3)"
                  >
                    {amount(decimal(hi))}
                  </text>
                  <text
                    x="50"
                    y="198"
                    textAnchor="end"
                    fontSize="9"
                    fill="var(--tx3)"
                  >
                    {amount(decimal(lo))}
                  </text>
                  {data.months.map((r, i) => (
                    <text
                      key={r.month}
                      x={x(i)}
                      y="220"
                      textAnchor="middle"
                      fill="var(--tx3)"
                      fontSize="10"
                    >
                      {r.month}
                    </text>
                  ))}
                </svg>
              </PanelBody>
            </Panel>
            <Panel>
              <PanelHeader
                title="Balance by account"
                subtitle="Today · base book value"
              />
              <PanelBody>
                <div className="flex min-h-[260px] flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    {data.accounts.length === 0 && (
                      <span className="text-tx3">
                        No bank or cash accounts yet.
                      </span>
                    )}
                    {data.accounts.map((b, i) => (
                      <div
                        key={b.id}
                        className="flex items-center gap-1.5 text-[11px]"
                      >
                        <span
                          className="size-2 shrink-0"
                          style={{ background: `var(--c${(i % 6) + 1})` }}
                        />
                        <Link
                          className="min-w-0 truncate"
                          href={`/banking/accounts/${b.id}`}
                        >
                          {b.name}
                        </Link>
                        <strong>{amount(b.book_value)}</strong>
                      </div>
                    ))}
                  </div>
                  <div className="flex flex-1 items-center justify-center">
                    <BalanceDonut banks={data.accounts} />
                  </div>
                </div>
              </PanelBody>
            </Panel>
          </div>
          <TransactionsTable recent />
          {tx && (
            <TransactionDrawer
              banks={data.accounts}
              onClose={() => setTx(false)}
            />
          )}
        </>
      )}
    </Screen>
  );
}
function BalanceDonut({ banks }: { banks: Bank[] }) {
  const amount = useMoney();
  const total = banks.reduce(
    (t, b) => t + (minor(b.book_value) > 0n ? minor(b.book_value) : 0n),
    0n,
  );
  let cursor = 0n;
  const stops: string[] = [];
  for (const [i, b] of banks.entries()) {
    const n = minor(b.book_value);
    if (n <= 0n || !total) continue;
    const next = cursor + (n * 36000n) / total;
    stops.push(
      `var(--c${(i % 6) + 1}) ${decimal(cursor, 2)}deg ${decimal(next, 2)}deg`,
    );
    cursor = next;
  }
  return (
    <div
      className="relative flex size-[200px] shrink-0 items-center justify-center"
      style={{
        background: stops.length
          ? `conic-gradient(${stops.join(",")})`
          : "var(--sf3)",
        clipPath: "circle(50%)",
      }}
    >
      <div
        className="absolute inset-8 bg-sf"
        style={{ clipPath: "circle(50%)" }}
      />
      <span className="relative flex flex-col items-center gap-1">
        <span className="text-[10px] uppercase text-tx3">Positive cash</span>
        <strong className="text-[16px]">{amount(decimal(total))}</strong>
      </span>
    </div>
  );
}
