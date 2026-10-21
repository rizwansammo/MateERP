"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Panel } from "@/components/ui/Panel";
import { Table, THead, TBody, TH, TR, TD } from "@/components/ui/Table";
import {
  FilterChips,
  Pager,
  SearchBox,
  SortHead,
  TableState,
  TableToolbar,
} from "@/components/ui/TableKit";
import { api, errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useDebounced } from "@/lib/useDebounced";

import {
  EntityDrawer,
  type FormField,
  type Page,
  QueryState,
  Screen,
  refreshFinance,
  useAccounts,
  useFinance,
  useMoney,
} from "./shared";
import type { Account, Report } from "./types";

const TYPES = ["asset", "liability", "equity", "revenue", "expense"];
export function AccountsPage() {
  const amount = useMoney();
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const q = useDebounced(search, 250);
  const [type, setType] = useState("all");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("code");
  const [edit, setEdit] = useState<Account | "new" | null>(null);
  const [setup, setSetup] = useState(false);
  const query = useFinance<Page<Account>>(
    `/accounting/accounts/?page=${page}&search=${encodeURIComponent(q)}&type=${type === "all" ? "" : type}&sort=${sort}`,
  );
  const all = useAccounts();
  const balances = useFinance<Report>("/accounting/ledger/");
  const fields: FormField[] = [
    { key: "code", label: "Code", required: true },
    { key: "name", label: "Account name", required: true },
    {
      key: "account_type",
      label: "Type",
      options: TYPES.map((t) => ({ value: t, label: t })),
    },
    { key: "subtype", label: "Group / subtype" },
    {
      key: "normal_side",
      label: "Normal balance",
      options: [
        { value: "debit", label: "Debit" },
        { value: "credit", label: "Credit" },
      ],
    },
    {
      key: "parent_id",
      label: "Parent summary account",
      type: "id",
      options: [
        { value: "", label: "No parent" },
        ...(all.data ?? [])
          .filter(
            (a) => !a.is_postable && (edit === "new" || a.id !== edit?.id),
          )
          .map((a) => ({
            value: String(a.id),
            label: `${a.code} · ${a.name}`,
          })),
      ],
    },
    {
      key: "currency",
      label: "Currency restriction",
      hint: "Leave blank for unrestricted; e.g. BDT or USD.",
    },
    {
      key: "control",
      label: "Control purpose",
      options: [
        { value: "", label: "Ordinary account" },
        { value: "fx_gain", label: "Exchange gains" },
        { value: "fx_loss", label: "Exchange losses" },
        { value: "retained_earnings", label: "Retained earnings" },
        { value: "receivable", label: "Accounts receivable — customer subledger" },
        { value: "payable", label: "Accounts payable — vendor subledger" },
        { value: "customer_credit", label: "Customer credits and advances" },
        { value: "founder_payable", label: "Founder reimbursable payables" },
        { value: "founder_loan", label: "Founder loan principal" },
        { value: "founder_pending", label: "Pending founder funding" },
        { value: "founder_equity", label: "Other contributed equity" },
        { value: "share_capital", label: "Recognized paid-in share capital" },
        { value: "share_premium", label: "Recognized share premium" },
      ],
    },
    { key: "description", label: "Description", type: "textarea" },
    {
      key: "is_postable",
      label: "Posting account (off for summary)",
      type: "checkbox",
    },
    { key: "is_active", label: "Active", type: "checkbox" },
  ];
  const depth = (a: Account) => {
    let n = 0,
      p = a.parent_id;
    const seen = new Set<number>();
    while (p && n < 15 && !seen.has(p)) {
      seen.add(p);
      n++;
      p = all.data?.find((x) => x.id === p)?.parent_id ?? null;
    }
    return n;
  };
  return (
    <Screen
      eyebrow="General ledger"
      title="Chart of accounts"
      description="Double-entry account structure. Summary accounts group the ledger; only active posting accounts accept entries."
      actions={
        can("accounting.manage") && (
          <>
            <Button onClick={() => setSetup(true)}>Set up starter chart</Button>
            <Button variant="primary" icon="add" onClick={() => setEdit("new")}>
              New account
            </Button>
          </>
        )
      }
    >
      <QueryState loading={false} error={balances.error} />
      <Panel>
        <TableToolbar>
          <FilterChips
            label="Account type"
            value={type}
            onChange={(v) => {
              setType(v);
              setPage(1);
            }}
            options={["all", ...TYPES].map((t) => ({
              value: t,
              label: t === "all" ? "All" : t[0]!.toUpperCase() + t.slice(1),
            }))}
          />
          <SearchBox
            value={search}
            onChange={(v) => {
              setSearch(v);
              setPage(1);
            }}
          />
        </TableToolbar>
        <Table className="min-w-[800px] table-fixed [&_th:nth-child(1)]:w-[80px] [&_th:nth-child(3)]:w-[100px] [&_th:nth-child(5)]:w-[150px] [&_th:nth-child(6)]:w-[90px]">
          <THead>
            <TR>
              <TH>
                <SortHead
                  label="Code"
                  active={sort.includes("code")}
                  dir={sort.startsWith("-") ? "desc" : "asc"}
                  onSort={() => setSort(sort === "code" ? "-code" : "code")}
                />
              </TH>
              <TH style={{ width: "calc((100% - 420px) * .625)" }}>Account</TH>
              <TH>Type</TH>
              <TH>Group</TH>
              <TH align="right">Balance</TH>
              <TH>Actions</TH>
            </TR>
          </THead>
          <TBody>
            <TableState
              colSpan={6}
              loading={query.loading}
              error={query.error ? errorMessage(query.error) : null}
              empty={
                query.data?.count === 0
                  ? "No accounts. Set up a starter chart or create your own accounts."
                  : null
              }
            >
              {query.data?.results.map((a) => (
                <TR key={a.id}>
                  <TD className="font-mono">{a.code}</TD>
                  <TD>
                    <div style={{ paddingLeft: depth(a) * 14 }}>
                      <Link href={`/banking/ledger/${a.id}`}>{a.name}</Link>
                      <div className="text-[11.5px] text-tx3">
                        {a.is_postable ? "Posting" : "Summary"}
                        {!a.is_active && " · Inactive"}
                        {a.control && ` · ${a.control}`}
                      </div>
                    </div>
                  </TD>
                  <TD>{a.account_type}</TD>
                  <TD>{a.subtype}</TD>
                  <TD align="right">
                    {amount(
                      balances.data
                        ? (balances.data.rows.find((r) => r.account_id === a.id)
                            ?.balance ?? "0")
                        : undefined,
                    )}
                  </TD>
                  <TD>
                    {can("accounting.manage") && (
                      <Button size="xs" onClick={() => setEdit(a)}>
                        Edit
                      </Button>
                    )}
                  </TD>
                </TR>
              ))}
            </TableState>
          </TBody>
        </Table>
        {query.data && (
          <Pager
            page={page}
            totalPages={query.data.total_pages}
            count={query.data.count}
            pageSize={query.data.page_size}
            onPage={setPage}
          />
        )}
      </Panel>
      {edit && (
        <EntityDrawer
          width={520}
          title={
            edit === "new" ? "New ledger account" : `Edit account ${edit.code}`
          }
          fields={fields}
          initial={
            edit === "new"
              ? {
                  code: "",
                  name: "",
                  account_type: "expense",
                  normal_side: "debit",
                  subtype: "",
                  parent_id: "",
                  currency: "",
                  control: "",
                  description: "",
                  is_active: true,
                  is_postable: true,
                }
              : {
                  ...edit,
                  id: String(edit.id),
                  parent_id: edit.parent_id ? String(edit.parent_id) : "",
                }
          }
          onClose={() => setEdit(null)}
          onSave={(data) =>
            edit === "new"
              ? api.post("/accounting/accounts/", data)
              : api.patch(`/accounting/accounts/${edit.id}/`, data)
          }
        />
      )}
      <ConfirmDialog
        open={setup}
        title="Set up starter chart"
        confirmLabel="Create chart"
        onCancel={() => setSetup(false)}
        onConfirm={async () => {
          await api.post("/accounting/accounts/setup/");
          refreshFinance();
          setSetup(false);
        }}
      >
        <p>
          The starter chart creates assets, liabilities, equity, income and
          expenses, including cash, bank, tax and FX accounts. It creates no
          balances. Existing charts are never overwritten.
        </p>
        <div className="text-[12px] text-tx3">
          You may instead create accounts individually using New account.
        </div>
        <Badge tone="info">No opening balances</Badge>
      </ConfirmDialog>
    </Screen>
  );
}
