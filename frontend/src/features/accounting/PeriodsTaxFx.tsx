"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Panel, PanelHeader } from "@/components/ui/Panel";
import { StatGrid } from "@/components/ui/StatGrid";
import { Table, THead, TBody, TH, TR, TD } from "@/components/ui/Table";
import { TableState, TableToolbar } from "@/components/ui/TableKit";
import { api, errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";

import {
  EntityDrawer,
  type FormField,
  type Page,
  QueryState,
  Screen,
  refreshFinance,
  today,
  useAccounts,
  useConfig,
  useFinance,
  useMoney,
} from "./shared";
import type { Period, Rate, Tax, Year } from "./types";

export function PeriodsPage() {
  const amount = useMoney();
  const { can } = useAuth();
  const config = useConfig();
  const years = useFinance<Page<Year>>(
    "/accounting/fiscal-years/?page_size=100",
  );
  const periods = useFinance<Page<Period>>(
    "/accounting/periods/?page_size=100",
  );
  const [create, setCreate] = useState(false);
  const [change, setChange] = useState<{
    id: number;
    closed: boolean;
    name: string;
    year: boolean;
  } | null>(null);
  return (
    <Screen
      title="Accounting periods"
      description="Fiscal years follow your company settings. Closed periods reject new postings; corrections use explicitly selected open periods."
      actions={
        can("accounting.manage") && (
          <Button variant="primary" icon="add" onClick={() => setCreate(true)}>
            New fiscal year
          </Button>
        )
      }
    >
      <QueryState loading={years.loading} error={years.error} />
      <StatGrid
        minWidth={180}
        stats={[
          {
            label: "Fiscal years",
            value: String(years.data?.count ?? "—"),
            accentBar: true,
          },
          {
            label: "Open periods",
            value: String(
              periods.data?.results.filter((p) => !p.is_closed).length ?? "—",
            ),
            accentBar: true,
          },
          {
            label: "Closed periods",
            value: String(
              periods.data?.results.filter((p) => p.is_closed).length ?? "—",
            ),
            accentBar: true,
          },
          {
            label: "Base currency",
            value: config.data?.base_currency ?? "—",
            accentBar: true,
          },
        ]}
      />
      <Panel>
        <PanelHeader title="Fiscal years" />
        <Table>
          <THead>
            <TR>
              <TH>Fiscal year</TH>
              <TH>Start</TH>
              <TH>End</TH>
              <TH>Status</TH>
              <TH>Actions</TH>
            </TR>
          </THead>
          <TBody>
            {years.data?.results.map((y) => (
              <TR key={y.id}>
                <TD>{y.name}</TD>
                <TD>{y.start}</TD>
                <TD>{y.end}</TD>
                <TD>
                  <Badge tone={y.is_closed ? "neutral" : "ok"}>
                    {y.is_closed ? "Closed" : "Open"}
                  </Badge>
                </TD>
                <TD>
                  {can("accounting.periods.manage") && (
                    <Button
                      size="xs"
                      onClick={() =>
                        setChange({
                          id: y.id,
                          closed: !y.is_closed,
                          name: y.name,
                          year: true,
                        })
                      }
                    >
                      {y.is_closed ? "Reopen year" : "Close year"}
                    </Button>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Panel>
      <Panel>
        <TableToolbar title="Accounting periods" />
        <Table>
          <THead>
            <TR>
              <TH>Period</TH>
              <TH>Status</TH>
              <TH align="right">Entries</TH>
              <TH align="right">Revenue</TH>
              <TH align="right">Expenses</TH>
              <TH>Closed by</TH>
              <TH>Actions</TH>
            </TR>
          </THead>
          <TBody>
            <TableState
              colSpan={7}
              loading={periods.loading}
              error={periods.error ? errorMessage(periods.error) : null}
              empty={
                periods.data?.count === 0
                  ? "Create a fiscal year to generate its monthly accounting periods."
                  : null
              }
            >
              {periods.data?.results.map((p) => (
                <TR key={p.id}>
                  <TD>
                    {p.start.slice(0, 7)}
                    <div className="text-[11.5px] text-tx3">
                      {p.start} — {p.end}
                    </div>
                  </TD>
                  <TD>
                    <Badge tone={p.is_closed ? "neutral" : "ok"}>
                      {p.is_closed ? "Closed · locked" : "Open"}
                    </Badge>
                  </TD>
                  <TD align="right">{p.entry_count ?? 0}</TD>
                  <TD align="right">{amount(p.revenue ?? "0")}</TD>
                  <TD align="right">{amount(p.expenses ?? "0")}</TD>
                  <TD>{p.closed_by_name || "—"}</TD>
                  <TD>
                    {can("accounting.periods.manage") && (
                      <Button
                        size="xs"
                        onClick={() =>
                          setChange({
                            id: p.id,
                            closed: !p.is_closed,
                            name: p.start.slice(0, 7),
                            year: false,
                          })
                        }
                      >
                        {p.is_closed ? "Reopen" : "Close"}
                      </Button>
                    )}
                  </TD>
                </TR>
              ))}
            </TableState>
          </TBody>
        </Table>
      </Panel>
      {create && (
        <EntityDrawer
          title="New fiscal year"
          fields={[
            {
              key: "start",
              label: "Fiscal year start",
              type: "date",
              required: true,
              hint: `Use the first day of month ${config.data?.fiscal_year_start_month ?? "configured in Company Profile"}.`,
            },
          ]}
          initial={{
            start: `${today().slice(0, 4)}-${String(config.data?.fiscal_year_start_month ?? 1).padStart(2, "0")}-01`,
          }}
          onClose={() => setCreate(false)}
          onSave={(data) => api.post("/accounting/fiscal-years/", data)}
        />
      )}
      <ConfirmDialog
        open={!!change}
        title={`${change?.closed ? "Close" : "Reopen"} ${change?.name ?? ""}?`}
        confirmLabel={change?.closed ? "Close period" : "Reopen period"}
        reason={change?.closed ? undefined : "required"}
        onCancel={() => setChange(null)}
        onConfirm={async (reason) => {
          if (!change) return;
          await api.post(
            `/accounting/${change.year ? "fiscal-years" : "periods"}/${change.id}/${change.closed ? "close" : "reopen"}/`,
            { reason },
          );
          refreshFinance();
          setChange(null);
        }}
      >
        {change?.closed
          ? "Closing locks posting dates. A fiscal-year close also closes its monthly periods."
          : "Reopening is a privileged, audited action. Prefer an adjustment in a current open period."}
      </ConfirmDialog>
    </Screen>
  );
}

export function RatesPanel() {
  const amount = useMoney();
  const { can } = useAuth();
  const config = useConfig();
  const rates = useFinance<Page<Rate>>(
    "/accounting/exchange-rates/?page_size=100",
  );
  const [add, setAdd] = useState(false);
  const [convertOpen, setConvertOpen] = useState(false);
  const [conversion, setConversion] = useState<{
    amount: string;
    currency: string;
    base_amount: string;
    base_currency: string;
    exchange_rate: string;
    source: string;
  } | null>(null);
  if (!can("finance.view")) return null;
  return (
    <>
      <Panel>
        <PanelHeader
          title="Exchange rate history"
          subtitle={`Base currency per 1 transaction-currency unit · ${config.data?.base_currency ?? ""}`}
          actions={
            can("accounting.manage") && (
              <div className="flex gap-2">
                <Button size="sm" onClick={() => setConvertOpen(true)}>
                  Preview conversion
                </Button>
                <Button
                  size="sm"
                  disabled={
                    !config.data?.enabled_currencies.some(
                      (c) => c !== config.data?.base_currency,
                    )
                  }
                  onClick={() => setAdd(true)}
                >
                  Add exchange rate
                </Button>
              </div>
            )
          }
        />
        <Table>
          <THead>
            <TR>
              <TH>Currency</TH>
              <TH>Effective from</TH>
              <TH align="right">Base per unit</TH>
              <TH>Source</TH>
            </TR>
          </THead>
          <TBody>
            <TableState
              colSpan={4}
              loading={rates.loading}
              error={rates.error ? errorMessage(rates.error) : null}
              empty={
                rates.data?.count === 0
                  ? "No foreign exchange rates. Base-currency postings use rate 1."
                  : null
              }
            >
              {rates.data?.results.map((r) => (
                <TR key={r.id}>
                  <TD className="font-mono">
                    {r.currency} / {r.base_currency}
                  </TD>
                  <TD>{r.effective_date}</TD>
                  <TD align="right">{r.value}</TD>
                  <TD>{r.source}</TD>
                </TR>
              ))}
            </TableState>
          </TBody>
        </Table>
      </Panel>
      {add && (
        <EntityDrawer
          title="Add exchange rate"
          width={480}
          fields={[
            {
              key: "currency",
              label: "Currency",
              options: (config.data?.enabled_currencies ?? [])
                .filter((c) => c !== config.data?.base_currency)
                .map((c) => ({ value: c, label: c })),
            },
            { key: "effective_date", label: "Effective from", type: "date" },
            { key: "value", label: "Base currency per 1 unit", type: "amount" },
            { key: "source", label: "Rate source / reason" },
          ]}
          initial={{
            currency:
              config.data?.enabled_currencies.find(
                (c) => c !== config.data?.base_currency,
              ) ?? "",
            effective_date: today(),
            value: "",
            source: "Manual",
          }}
          onSave={(data) => api.post("/accounting/exchange-rates/", data)}
          onClose={() => setAdd(false)}
        >
          <div className="mt-4">
            <Banner tone="info">
              Each save creates a permanent rate revision. Posted transactions
              keep their historical rate snapshots.
            </Banner>
          </div>
        </EntityDrawer>
      )}
      {convertOpen && (
        <EntityDrawer
          title="Currency conversion preview"
          width={480}
          fields={[
            {
              key: "currency",
              label: "Currency",
              options: (config.data?.enabled_currencies ?? []).map((c) => ({
                value: c,
                label: c,
              })),
            },
            { key: "on", label: "Conversion date", type: "date" },
            { key: "amount", label: "Amount", type: "amount" },
          ]}
          initial={{
            currency: config.data?.base_currency ?? "",
            on: today(),
            amount: "",
          }}
          onClose={() => {
            setConvertOpen(false);
            setConversion(null);
          }}
          saveLabel="Preview conversion"
          onSave={async (data) => {
            setConversion(
              await api.post("/accounting/exchange-rates/preview/", data),
            );
            return false;
          }}
        >
          {conversion && (
            <div className="mt-4">
              <Banner tone="info">
                Last preview: {amount(conversion.amount, conversion.currency)} ={" "}
                {amount(conversion.base_amount, conversion.base_currency)} ·
                Rate {conversion.exchange_rate} · {conversion.source}. No
                financial entry is created.
              </Banner>
            </div>
          )}
        </EntityDrawer>
      )}
    </>
  );
}

export function TaxPage() {
  const amount = useMoney();
  const { can } = useAuth();
  const accounts = useAccounts();
  const taxes = useFinance<Page<Tax>>("/accounting/tax-codes/?page_size=100");
  const position = useFinance<{ input: string; output: string; net: string }>(
    "/accounting/tax-position/",
  );
  const [edit, setEdit] = useState<Tax | "new" | null>(null);
  const options = (type: string) => [
    { value: "", label: "Select account" },
    ...(accounts.data ?? [])
      .filter((a) => a.account_type === type && a.is_postable && a.is_active)
      .map((a) => ({ value: String(a.id), label: `${a.code} · ${a.name}` })),
  ];
  const fields: FormField[] = [
    { key: "code", label: "Code", required: true },
    { key: "name", label: "Name", required: true },
    { key: "percent", label: "Rate %", type: "amount" },
    { key: "effective_date", label: "Effective from", type: "date" },
    {
      key: "input_account_id",
      label: "Input tax receivable account",
      type: "id",
      options: options("asset"),
    },
    {
      key: "output_account_id",
      label: "Output tax payable account",
      type: "id",
      options: options("liability"),
    },
    { key: "description", label: "Description", type: "textarea" },
    { key: "is_active", label: "Active", type: "checkbox" },
  ];
  const revision = edit && edit !== "new" ? edit.revisions[0] : undefined;
  return (
    <Screen
      title="Tax codes & tax position"
      description="Tax categories and mapped ledger accounts for manual tax journals. Billing calculations arrive in Phase 4; filing is not provided."
      actions={
        can("accounting.manage") && (
          <Button variant="primary" icon="add" onClick={() => setEdit("new")}>
            New tax code
          </Button>
        )
      }
    >
      <StatGrid
        stats={[
          {
            label: "Input tax",
            value: amount(position.data?.input),
            accentBar: true,
          },
          {
            label: "Output tax",
            value: amount(position.data?.output),
            accentBar: true,
          },
          {
            label: "Net payable position",
            value: amount(position.data?.net),
            accentBar: true,
          },
        ]}
      />
      <QueryState loading={position.loading} error={position.error} />
      <Panel>
        <Table>
          <THead>
            <TR>
              <TH>Code</TH>
              <TH>Name</TH>
              <TH align="right">Rate</TH>
              <TH>Effective from</TH>
              <TH>Description</TH>
              <TH>Status</TH>
              <TH>Actions</TH>
            </TR>
          </THead>
          <TBody>
            <TableState
              colSpan={7}
              loading={taxes.loading}
              error={taxes.error ? errorMessage(taxes.error) : null}
              empty={
                taxes.data?.count === 0 ? "No tax codes configured." : null
              }
            >
              {taxes.data?.results.map((t) => (
                <TR key={t.id}>
                  <TD className="font-mono">{t.code}</TD>
                  <TD>{t.name}</TD>
                  <TD align="right">{t.revisions[0]?.percent ?? "—"}%</TD>
                  <TD>{t.revisions[0]?.effective_date ?? "—"}</TD>
                  <TD>{t.description}</TD>
                  <TD>
                    <Badge tone={t.is_active ? "ok" : "neutral"}>
                      {t.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </TD>
                  <TD>
                    {can("accounting.manage") && (
                      <Button size="xs" onClick={() => setEdit(t)}>
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
      {edit && (
        <EntityDrawer
          title={edit === "new" ? "New tax code" : `Edit ${edit.code}`}
          fields={fields}
          initial={{
            code: edit === "new" ? "" : edit.code,
            name: edit === "new" ? "" : edit.name,
            percent: revision?.percent ?? "",
            effective_date: today(),
            input_account_id: revision ? String(revision.input_account) : "",
            output_account_id: revision ? String(revision.output_account) : "",
            description: edit === "new" ? "" : edit.description,
            is_active: edit === "new" ? true : edit.is_active,
          }}
          onClose={() => setEdit(null)}
          onSave={(data) => {
            const {
              percent,
              effective_date,
              input_account_id,
              output_account_id,
              ...rest
            } = data;
            const payload = {
              ...rest,
              revision: {
                percent,
                effective_date,
                input_account_id,
                output_account_id,
              },
            };
            return edit === "new"
              ? api.post("/accounting/tax-codes/", payload)
              : api.patch(`/accounting/tax-codes/${edit.id}/`, payload);
          }}
        />
      )}
    </Screen>
  );
}
