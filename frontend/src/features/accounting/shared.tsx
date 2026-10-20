"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type ReactNode, useState } from "react";

import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Choice";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Field } from "@/components/ui/Field";
import { Input, Select, Textarea } from "@/components/ui/Input";
import {
  Cell,
  DialogActions,
  DialogFooter,
  Drawer,
  FormGrid,
} from "@/components/ui/Overlay";
import { PageContainer, PageHeader } from "@/components/ui/PageHeader";
import { Restricted } from "@/components/ui/Restricted";
import { Spinner } from "@/components/ui/Spinner";
import { toast } from "@/components/ui/Toast";
import { ApiError, api, errorMessage } from "@/lib/api/client";
import { useCurrencies } from "@/lib/api/hooks";
import { invalidate, useQuery } from "@/lib/api/query";
import type { Page } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useFormState, useUnsavedGuard } from "@/lib/forms";

import type { Account, Config, Period } from "./types";
import { amount as formatAmount } from "./money";

export const ROOT = "/accounting/";
export function refreshFinance() {
  invalidate(ROOT);
  invalidate("/banking/");
  invalidate("/approvals/");
}
export function useFinance<T>(path: string | null) {
  return useQuery(path, () => api.get<T>(path!));
}
export function useAccounts() {
  return useFinance<Account[]>("/accounting/accounts/tree/");
}
export function useConfig() {
  return useFinance<Config>("/accounting/config/");
}
export function useMoney() {
  const config = useConfig();
  const currencies = useCurrencies();
  return (value: string | undefined, currency?: string) => {
    const code = currency ?? config.data?.base_currency ?? "";
    const formatted = formatAmount(
      value,
      code,
      config.data?.number_grouping ?? "international",
    );
    if (
      value !== undefined &&
      code &&
      config.data?.currency_display === "symbol"
    ) {
      const symbol = currencies.data?.find((c) => c.code === code)?.symbol;
      if (symbol) return symbol + formatted.slice(code.length + 1);
    }
    return formatted;
  };
}
export function today() {
  return new Date().toLocaleDateString("en-CA");
}
export function key() {
  return crypto.randomUUID();
}
export const linkClass =
  "inline-flex h-[30px] items-center border border-bd2 bg-sf px-[11px] text-[12px] font-medium text-tx hover:bg-sf3 hover:text-tx hover:no-underline";
export function JournalLink({
  id,
  children,
}: {
  id: string;
  children: ReactNode;
}) {
  return (
    <Link className="font-mono text-[12px]" href={`/banking/journals/${id}`}>
      {children}
    </Link>
  );
}
export function Screen({
  title,
  description,
  actions,
  children,
  eyebrow = "Banking & Accounting",
}: {
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
  eyebrow?: string;
}) {
  return (
    <PageContainer>
      <PageHeader
        eyebrow={eyebrow}
        title={title}
        description={description}
        actions={actions}
      />
      {children}
    </PageContainer>
  );
}
export function FinancialGate({ children }: { children: ReactNode }) {
  const { can } = useAuth();
  return can("finance.view") ? (
    children
  ) : (
    <Restricted title="Access restricted">
      Your role does not include financial records.
    </Restricted>
  );
}
export function QueryState({
  loading,
  error,
}: {
  loading: boolean;
  error: unknown;
}) {
  if (error) return <Banner tone="err">{errorMessage(error)}</Banner>;
  if (loading)
    return (
      <span className="flex items-center gap-2 text-[12.5px] text-tx3">
        <Spinner /> Loading…
      </span>
    );
  return null;
}
export function AccountSelect({
  value,
  onChange,
  accounts,
  label = "Account",
  summary = false,
}: {
  value: string;
  onChange: (value: string) => void;
  accounts: Account[];
  label?: string;
  summary?: boolean;
}) {
  return (
    <Select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">Select account</option>
      {accounts
        .filter((a) => a.is_active && (summary || a.is_postable))
        .map((a) => (
          <option key={a.id} value={a.id}>
            {a.code} · {a.name}
          </option>
        ))}
    </Select>
  );
}
export function DateFilters({
  from,
  to,
  onFrom,
  onTo,
}: {
  from: string;
  to: string;
  onFrom: (s: string) => void;
  onTo: (s: string) => void;
}) {
  const periods = useFinance<Page<Period>>(
    "/accounting/periods/?page_size=100",
  );
  const selected = periods.data?.results.find(
    (p) => p.start === from && p.end === to,
  );
  return (
    <div className="flex flex-wrap items-center gap-3 text-[12px] text-tx3">
      <span className="w-[180px]">
        <Select
          controlSize="sm"
          aria-label="Accounting period"
          value={selected?.id ?? ""}
          onChange={(e) => {
            const p = periods.data?.results.find(
              (x) => String(x.id) === e.target.value,
            );
            if (p) {
              onFrom(p.start);
              onTo(p.end);
            }
          }}
        >
          <option value="">Custom date range</option>
          {periods.data?.results.map((p) => (
            <option key={p.id} value={p.id}>
              {p.start.slice(0, 7)}
              {p.is_closed ? " · closed" : ""}
            </option>
          ))}
        </Select>
      </span>
      <label className="flex items-center gap-2">
        From{" "}
        <span className="w-[145px]">
          <Input
            controlSize="sm"
            aria-label="From date"
            type="date"
            value={from}
            onChange={(e) => onFrom(e.target.value)}
          />
        </span>
      </label>
      <label className="flex items-center gap-2">
        To{" "}
        <span className="w-[145px]">
          <Input
            controlSize="sm"
            aria-label="To date"
            type="date"
            value={to}
            onChange={(e) => onTo(e.target.value)}
          />
        </span>
      </label>
    </div>
  );
}
export function useRange() {
  const config = useConfig();
  const params = useSearchParams();
  const [chosenFrom, setFrom] = useState<string | null>(params.get("from"));
  const [to, setTo] = useState(params.get("to") ?? today());
  const month = config.data?.fiscal_year_start_month ?? 1;
  const year =
    Number(today().slice(0, 4)) - (Number(today().slice(5, 7)) < month ? 1 : 0);
  const from = chosenFrom ?? `${year}-${String(month).padStart(2, "0")}-01`;
  return { from, to, setFrom, setTo, query: `from=${from}&to=${to}` };
}

export interface FormField {
  key: string;
  label: string;
  type?: "text" | "date" | "checkbox" | "textarea" | "id" | "amount";
  required?: boolean;
  options?: { value: string; label: string }[];
  hint?: string;
}
export function EntityDrawer({
  title,
  fields,
  initial,
  onSave,
  onClose,
  width = 640,
  children,
  saveLabel = "Save",
  extraDirty = false,
}: {
  title: string;
  fields: FormField[];
  initial: Record<string, string | boolean>;
  onSave: (data: Record<string, unknown>) => Promise<unknown>;
  onClose: () => void;
  width?: number;
  children?: ReactNode;
  saveLabel?: string;
  extraDirty?: boolean;
}) {
  const form = useFormState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [discard, setDiscard] = useState(false);
  useUnsavedGuard(form.dirty || extraDirty);
  const close = () => {
    if (!busy) {
      if (form.dirty || extraDirty) setDiscard(true);
      else onClose();
    }
  };
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const data: Record<string, unknown> = { ...form.values };
      for (const f of fields)
        if (f.type === "id")
          data[f.key] = data[f.key] === "" ? null : Number(data[f.key]);
      const result = await onSave(data);
      if (result === false) return;
      refreshFinance();
      toast(
        result &&
          typeof result === "object" &&
          "status" in result &&
          result.status === "pending"
          ? "Submitted for approval. Review Journal entries."
          : "Changes saved",
      );
      onClose();
    } catch (e) {
      const message = form.applyError(e);
      const hidden =
        e instanceof ApiError
          ? Object.entries(e.fieldErrors())
              .filter(([name]) => !fields.some((f) => f.key === name))
              .map(([, value]) => value)
              .join(" · ")
          : "";
      setError(hidden || message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Drawer
        open
        title={title}
        eyebrow="Banking & Accounting"
        width={width}
        onClose={close}
        footer={
          <DialogFooter>
            {error && <Banner tone="err">{error}</Banner>}
            <DialogActions>
              <Button disabled={busy} onClick={close}>
                Cancel
              </Button>
              <Button
                variant="primary"
                disabled={busy}
                onClick={() => void save()}
              >
                {busy ? "Saving…" : saveLabel}
              </Button>
            </DialogActions>
          </DialogFooter>
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <FormGrid>
            {fields.map((f) => (
              <Cell key={f.key} w={f.type === "textarea" ? "full" : "half"}>
                {f.type === "checkbox" ? (
                  <Checkbox
                    checked={Boolean(form.values[f.key])}
                    onChange={(v) => form.set(f.key, v)}
                    label={f.label}
                  />
                ) : (
                  <Field
                    label={f.label}
                    htmlFor={`finance-${f.key}`}
                    required={f.required}
                    hint={f.hint}
                    error={form.errors[f.key]}
                  >
                    {f.options ? (
                      <Select
                        aria-label={f.label}
                        id={`finance-${f.key}`}
                        value={String(form.values[f.key] ?? "")}
                        onChange={(e) => form.set(f.key, e.target.value)}
                      >
                        {f.options.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </Select>
                    ) : f.type === "textarea" ? (
                      <Textarea
                        aria-label={f.label}
                        id={`finance-${f.key}`}
                        value={String(form.values[f.key] ?? "")}
                        onChange={(e) => form.set(f.key, e.target.value)}
                      />
                    ) : (
                      <Input
                        aria-label={f.label}
                        id={`finance-${f.key}`}
                        type={f.type === "date" ? "date" : "text"}
                        inputMode={f.type === "amount" ? "decimal" : undefined}
                        value={String(form.values[f.key] ?? "")}
                        onChange={(e) => form.set(f.key, e.target.value)}
                      />
                    )}
                  </Field>
                )}
              </Cell>
            ))}
          </FormGrid>
          {children}
        </form>
      </Drawer>
      <ConfirmDialog
        open={discard}
        title="Discard unsaved changes?"
        confirmLabel="Discard"
        danger
        onCancel={() => setDiscard(false)}
        onConfirm={onClose}
      />
    </>
  );
}
export type { Page };
