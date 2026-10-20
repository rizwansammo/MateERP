"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Field } from "@/components/ui/Field";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { DialogActions, DialogFooter, Drawer } from "@/components/ui/Overlay";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/Panel";
import { StatGrid } from "@/components/ui/StatGrid";
import { Table, THead, TBody, TH, TR, TD } from "@/components/ui/Table";
import {
  FilterChips,
  Pager,
  SearchBox,
  TableState,
  TableToolbar,
} from "@/components/ui/TableKit";
import { toast } from "@/components/ui/Toast";
import { ApiError, api, errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useUnsavedGuard } from "@/lib/forms";
import { useDebounced } from "@/lib/useDebounced";

import { decimal, minor } from "./money";
import {
  AccountSelect,
  DateFilters,
  EntityDrawer,
  JournalLink,
  type Page,
  QueryState,
  Screen,
  key,
  refreshFinance,
  today,
  useAccounts,
  useConfig,
  useFinance,
  useRange,
  useMoney,
} from "./shared";
import type { Journal, Tax } from "./types";

export function JournalStatus({ journal }: { journal: Journal }) {
  return (
    <Badge
      tone={
        journal.status === "posted"
          ? "ok"
          : journal.status === "pending"
            ? "warn"
            : "neutral"
      }
    >
      {journal.reversed_by_id
        ? "Reversed"
        : journal.approval_status === "rejected" ||
            journal.approval_status === "cancelled"
          ? `${journal.approval_status} · unposted`
          : journal.status === "pending"
            ? "Awaiting approval"
            : journal.status}
    </Badge>
  );
}
export function JournalsPage({ id }: { id?: string }) {
  return id ? <JournalDetail id={id} /> : <JournalDirectory />;
}
function JournalDirectory() {
  const amount = useMoney();
  const { can } = useAuth();
  const router = useRouter();
  const range = useRange();
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search, 250);
  const [status, setStatus] = useState("all");
  const [source, setSource] = useState("");
  const [page, setPage] = useState(1);
  const [edit, setEdit] = useState<"manual" | "opening" | null>(null);
  const query = useFinance<Page<Journal>>(
    `/accounting/journals/?page=${page}&search=${encodeURIComponent(debounced)}&kind=${source}&status=${status === "all" ? "" : status}&${range.query}`,
  );
  return (
    <Screen
      title="Journal entries"
      description="Manual journals and every system-generated posting. Posted entries are immutable; corrections use traceable reversals."
      actions={
        can("accounting.manage") && (
          <>
            <Button onClick={() => setEdit("opening")}>Opening balances</Button>
            <Button
              variant="primary"
              icon="add"
              onClick={() => setEdit("manual")}
            >
              New journal
            </Button>
          </>
        )
      }
    >
      <DateFilters {...range} onFrom={range.setFrom} onTo={range.setTo} />
      <Panel>
        <TableToolbar>
          <span className="w-[160px]">
            <Select
              controlSize="sm"
              aria-label="Journal source"
              value={source}
              onChange={(e) => {
                setSource(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All sources</option>
              {[
                "manual",
                "opening",
                "adjustment",
                "transfer",
                "bank_adjustment",
                "reversal",
              ].map((s) => (
                <option key={s} value={s}>
                  {s.replace("_", " ")}
                </option>
              ))}
            </Select>
          </span>
          <FilterChips
            label="Journal status"
            value={status}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
            options={["all", "draft", "pending", "posted"].map((v) => ({
              value: v,
              label:
                v === "pending"
                  ? "Awaiting approval"
                  : v[0]!.toUpperCase() + v.slice(1),
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
        <Table>
          <THead>
            <TR>
              <TH>Journal</TH>
              <TH>Date</TH>
              <TH>Narration</TH>
              <TH>Status</TH>
              <TH>Created by</TH>
              <TH align="right">Amount</TH>
            </TR>
          </THead>
          <TBody>
            <TableState
              colSpan={6}
              loading={query.loading}
              error={query.error ? errorMessage(query.error) : null}
              empty={
                query.data?.count === 0
                  ? "No journal entries in this range."
                  : null
              }
            >
              {query.data?.results.map((j) => (
                <TR key={j.id}>
                  <TD>
                    <JournalLink id={j.id}>{j.number ?? "Draft"}</JournalLink>
                  </TD>
                  <TD className="whitespace-nowrap">{j.posting_date}</TD>
                  <TD>
                    <Link href={`/banking/journals/${j.id}`}>
                      {j.description}
                    </Link>
                    <div className="text-[11.5px] text-tx3">
                      {j.kind} · {j.source_type}
                    </div>
                  </TD>
                  <TD>
                    <JournalStatus journal={j} />
                  </TD>
                  <TD>{j.created_by_name}</TD>
                  <TD align="right">
                    {amount(
                      decimal(
                        j.lines.reduce((v, l) => v + minor(l.base_debit), 0n),
                      ),
                      j.base_currency,
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
        <JournalEditor
          kind={edit}
          onClose={() => setEdit(null)}
          onSaved={(j) => router.push(`/banking/journals/${j.id}`)}
        />
      )}
    </Screen>
  );
}
function JournalDetail({ id }: { id: string }) {
  const amount = useMoney();
  const router = useRouter();
  const { can } = useAuth();
  const query = useFinance<Journal>(`/accounting/journals/${id}/`);
  const history = useFinance<{
    events: {
      action: string;
      occurred_at: string;
      actor_label: string;
      reason: string;
    }[];
  }>(`/accounting/journals/${id}/history/`);
  const [edit, setEdit] = useState(false);
  const [reverse, setReverse] = useState(false);
  const [confirmPost, setConfirmPost] = useState(false);
  const postingKey = useRef(key());
  const j = query.data;
  const totals = j
    ? j.lines.reduce(
        (v, l) => ({
          d: v.d + minor(l.base_debit),
          c: v.c + minor(l.base_credit),
        }),
        { d: 0n, c: 0n },
      )
    : null;
  return (
    <Screen
      title={
        j
          ? `${j.number ?? "Draft journal"} — ${j.description}`
          : "Journal details"
      }
      description={
        j
          ? `${j.posting_date} · created by ${j.created_by_name} · ${j.base_currency}`
          : "Journal and posting history"
      }
      actions={
        j &&
        can("accounting.manage") && (
          <>
            {(j.status === "draft" ||
              (j.status === "pending" &&
                ["rejected", "cancelled"].includes(j.approval_status ?? ""))) &&
              ["manual", "opening", "adjustment"].includes(j.source_type) && (
                <>
                  <Button onClick={() => setEdit(true)}>Edit draft</Button>
                  <Button
                    variant="primary"
                    disabled={j.status !== "draft"}
                    onClick={() => setConfirmPost(true)}
                  >
                    Post journal
                  </Button>
                </>
              )}
            {j.status === "posted" &&
              !j.reversed_by_id &&
              !j.reversal_of_id && (
                <Button icon="undo" onClick={() => setReverse(true)}>
                  Reverse
                </Button>
              )}
          </>
        )
      }
    >
      <QueryState loading={query.loading} error={query.error} />
      {j && totals && (
        <>
          <StatGrid
            minWidth={180}
            stats={[
              {
                label: "Debits",
                value: amount(decimal(totals.d), j.base_currency),
                accentBar: true,
              },
              {
                label: "Credits",
                value: amount(decimal(totals.c), j.base_currency),
                accentBar: true,
              },
              {
                label: "Difference",
                value: amount(decimal(totals.d - totals.c), j.base_currency),
                tone: totals.d === totals.c ? "ok" : "err",
              },
            ]}
          />
          <div>
            <JournalStatus journal={j} />
          </div>
          {j.status === "pending" && (
            <Banner tone="warn">
              {["rejected", "cancelled"].includes(j.approval_status ?? "")
                ? "The request was closed without posting. Edit manual drafts to revalidate and resubmit; record a new bank transaction for a rejected treasury request."
                : "Awaiting approval; these lines have no effect on ledger balances."}{" "}
              <Link href="/settings/approvals">Review approval request</Link>
            </Banner>
          )}
          {j.reversal_of_id && (
            <Banner tone="info">
              Reversal of{" "}
              <JournalLink id={j.reversal_of_id}>
                the original journal
              </JournalLink>
              . {j.reason}
            </Banner>
          )}
          {j.reversed_by_id && (
            <Banner tone="neutral">
              Reversed by{" "}
              <JournalLink id={j.reversed_by_id}>a linked journal</JournalLink>.
              Both entries remain in the ledger.
            </Banner>
          )}
          <Panel>
            <PanelHeader title="Lines" />
            <Table>
              <THead>
                <TR>
                  <TH>Account</TH>
                  <TH>Memo / currency & rate</TH>
                  <TH align="right">Debit</TH>
                  <TH align="right">Credit</TH>
                </TR>
              </THead>
              <TBody>
                {j.lines.map((l) => (
                  <TR key={l.id}>
                    <TD>
                      <Link href={`/banking/ledger/${l.account_id}`}>
                        {l.account_code} · {l.account_name}
                      </Link>
                    </TD>
                    <TD>
                      {l.description}
                      <div className="text-[11.5px] text-tx3">
                        {l.currency} · {l.exchange_rate} · {l.rate_source}
                      </div>
                    </TD>
                    <TD align="right">{amount(l.base_debit)}</TD>
                    <TD align="right">{amount(l.base_credit)}</TD>
                  </TR>
                ))}
                <TR className="bg-sf2 font-semibold">
                  <TD>Totals</TD>
                  <TD>{j.base_currency}</TD>
                  <TD align="right">{amount(decimal(totals.d))}</TD>
                  <TD align="right">{amount(decimal(totals.c))}</TD>
                </TR>
              </TBody>
            </Table>
          </Panel>
          <Panel>
            <PanelHeader title="Journal history" />
            <PanelBody>
              <QueryState loading={history.loading} error={history.error} />
              {history.data?.events.map((h, i) => (
                <div
                  className="flex flex-wrap gap-3 border-b border-bd py-2 text-[12px]"
                  key={i}
                >
                  <span>{h.occurred_at}</span>
                  <strong>
                    {h.action.replace("accounting.", "").replaceAll("_", " ")}
                  </strong>
                  <span>{h.actor_label}</span>
                  <span>{h.reason}</span>
                </div>
              ))}
            </PanelBody>
          </Panel>
          {edit && (
            <JournalEditor
              journal={j}
              kind={j.kind}
              onClose={() => setEdit(false)}
              onSaved={() => {
                setEdit(false);
                refreshFinance();
              }}
            />
          )}
          {reverse && (
            <EntityDrawer
              title={`Reverse ${j.number}`}
              width={500}
              fields={[
                {
                  key: "posting_date",
                  label: "Reversal date",
                  type: "date",
                  required: true,
                },
                {
                  key: "reason",
                  label: "Reason",
                  type: "textarea",
                  required: true,
                },
              ]}
              initial={{ posting_date: today(), reason: "" }}
              onClose={() => setReverse(false)}
              onSave={async (data) => {
                const next = await api.post<Journal>(
                  `/accounting/journals/${id}/reverse/`,
                  { ...data, posting_key: postingKey.current },
                );
                router.push(`/banking/journals/${next.id}`);
              }}
            />
          )}
        </>
      )}
      <ConfirmDialog
        open={confirmPost}
        title="Post journal?"
        confirmLabel="Post journal"
        onCancel={() => setConfirmPost(false)}
        onConfirm={async () => {
          const r = await api.post<{ status: string }>(
            `/accounting/journals/${id}/post/`,
            { posting_key: postingKey.current },
          );
          toast(
            r.status === "pending_approval"
              ? "Submitted for approval"
              : "Journal posted",
          );
          refreshFinance();
          setConfirmPost(false);
        }}
      >
        Posting creates an immutable financial record. If approval is required,
        the journal stays pending until an authorized decision.
      </ConfirmDialog>
    </Screen>
  );
}

interface DraftLine {
  tax_revision_id: string;
  account_id: string;
  description: string;
  currency: string;
  debit: string;
  credit: string;
  exchange_rate: string;
  rate_source: string;
}
const blankLine = (currency: string): DraftLine => ({
  tax_revision_id: "",
  account_id: "",
  description: "",
  currency,
  debit: "",
  credit: "",
  exchange_rate: "",
  rate_source: "",
});
export function JournalEditor({
  journal,
  kind = "manual",
  onClose,
  onSaved,
}: {
  journal?: Journal;
  kind?: string;
  onClose: () => void;
  onSaved: (j: Journal) => void;
}) {
  const amount = useMoney();
  const accounts = useAccounts();
  const taxes = useFinance<Page<Tax>>("/accounting/tax-codes/?page_size=100");
  const config = useConfig();
  const base = journal?.base_currency ?? config.data?.base_currency ?? "";
  const [description, setDescription] = useState(journal?.description ?? "");
  const [date, setDate] = useState(journal?.posting_date ?? today());
  const [reason, setReason] = useState(journal?.reason ?? "");
  const [lines, setLines] = useState<DraftLine[]>(
    journal
      ? journal.lines.map((l) => ({
          tax_revision_id: l.tax_revision_id ? String(l.tax_revision_id) : "",
          account_id: String(l.account_id),
          description: l.description,
          currency: l.currency,
          debit: minor(l.debit) ? l.debit : "",
          credit: minor(l.credit) ? l.credit : "",
          exchange_rate: l.exchange_rate,
          rate_source: l.rate_source,
        }))
      : [blankLine(""), blankLine("")],
  );
  const [saved, setSaved] = useState(journal);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [discard, setDiscard] = useState(false);
  const [initial] = useState(() =>
    JSON.stringify({ description, date, reason, lines }),
  );
  const dirty =
    JSON.stringify({ description, date, reason, lines }) !== initial;
  useUnsavedGuard(dirty);
  const postingKey = useRef(key());
  const update = (i: number, field: keyof DraftLine, value: string) => {
    setLines((old) =>
      old.map((l, n) => (n === i ? { ...l, [field]: value } : l)),
    );
    postingKey.current = key();
  };
  const close = () => {
    if (!busy) {
      if (dirty) setDiscard(true);
      else onClose();
    }
  };
  let totalD = 0n,
    totalC = 0n,
    invalid = false;
  try {
    for (const l of lines) {
      totalD += minor(l.debit || "0");
      totalC += minor(l.credit || "0");
    }
  } catch {
    invalid = true;
  }
  const mixed = lines.some((l) => l.currency && l.currency !== base);
  const submit = async (post: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const payload = {
        kind,
        description,
        posting_date: date,
        reason,
        ...(saved ? { revision: saved.revision } : {}),
        lines: lines.map((l) => ({
          ...(l.tax_revision_id
            ? { tax_revision_id: Number(l.tax_revision_id) }
            : {}),
          account_id: Number(l.account_id),
          description: l.description,
          currency: l.currency || base,
          debit: l.debit || "0",
          credit: l.credit || "0",
          ...(l.exchange_rate
            ? { exchange_rate: l.exchange_rate, rate_source: l.rate_source }
            : {}),
        })),
      };
      let j = saved
        ? await api.patch<Journal>(`/accounting/journals/${saved.id}/`, payload)
        : await api.post<Journal>("/accounting/journals/", payload);
      setSaved(j);
      if (post) {
        const r = await api.post<{ journal: Journal; status: string }>(
          `/accounting/journals/${j.id}/post/`,
          { posting_key: postingKey.current },
        );
        j = r.journal;
        toast(
          r.status === "pending_approval"
            ? "Submitted for approval"
            : "Journal posted",
        );
      } else toast("Draft saved");
      refreshFinance();
      onSaved(j);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? Object.values(e.fieldErrors()).join(" · ") || e.message
          : errorMessage(e),
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Drawer
        open
        width={900}
        title={
          kind === "opening"
            ? "Opening balances"
            : journal
              ? "Edit journal draft"
              : "New journal entry"
        }
        eyebrow="General ledger"
        onClose={close}
        footer={
          <DialogFooter>
            <div className="flex flex-wrap justify-end gap-7 text-[12px]">
              <span>
                Total debits{" "}
                <strong>
                  {invalid ? "Invalid amount" : amount(decimal(totalD))}
                </strong>
              </span>
              <span>
                Total credits{" "}
                <strong>
                  {invalid ? "Invalid amount" : amount(decimal(totalC))}
                </strong>
              </span>
              <span
                className={
                  invalid || totalD !== totalC ? "text-err" : "text-ok"
                }
              >
                {mixed
                  ? "Mixed currencies: base totals validated on the server"
                  : `Difference ${amount(decimal(totalD - totalC))}`}
              </span>
            </div>
            {error && <Banner tone="err">{error}</Banner>}
            <DialogActions>
              <Button disabled={busy} onClick={close}>
                Cancel
              </Button>
              <Button disabled={busy} onClick={() => void submit(false)}>
                Save draft
              </Button>
              <Button
                variant="primary"
                disabled={busy || invalid || !base}
                onClick={() => void submit(true)}
              >
                {busy ? "Working…" : "Post journal"}
              </Button>
            </DialogActions>
          </DialogFooter>
        }
      >
        <div className="flex flex-col gap-4">
          <QueryState
            loading={accounts.loading || config.loading}
            error={accounts.error || config.error}
          />
          {kind === "opening" && (
            <Banner tone="info">
              Enter existing account balances and explicit opening equity. Every
              difference must be explained by a visible line. Only one initial
              opening journal is allowed.
            </Banner>
          )}
          <div className="grid grid-cols-4 gap-3.5">
            <Field label="Journal date" htmlFor="journal-date">
              <Input
                id="journal-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </Field>
            <div className="col-span-3">
              <Field label="Narration" htmlFor="journal-description" required>
                <Input
                  id="journal-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </Field>
            </div>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Account</TH>
                  <TH>Memo</TH>
                  <TH>Currency</TH>
                  <TH align="right">Debit</TH>
                  <TH align="right">Credit</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {lines.map((l, i) => (
                  <TR key={i}>
                    <TD>
                      <span className="inline-block min-w-[195px]">
                        <AccountSelect
                          accounts={accounts.data ?? []}
                          label={`Line ${i + 1} account`}
                          value={l.account_id}
                          onChange={(v) => update(i, "account_id", v)}
                        />
                      </span>
                    </TD>
                    <TD>
                      <Input
                        aria-label={`Line ${i + 1} memo`}
                        value={l.description}
                        onChange={(e) =>
                          update(i, "description", e.target.value)
                        }
                      />
                    </TD>
                    <TD>
                      <Select
                        aria-label={`Line ${i + 1} currency`}
                        value={l.currency || base}
                        onChange={(e) => update(i, "currency", e.target.value)}
                      >
                        {config.data?.enabled_currencies.map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </Select>
                    </TD>
                    <TD>
                      <Input
                        aria-label={`Line ${i + 1} debit`}
                        inputMode="decimal"
                        value={l.debit}
                        onChange={(e) => update(i, "debit", e.target.value)}
                      />
                    </TD>
                    <TD>
                      <Input
                        aria-label={`Line ${i + 1} credit`}
                        inputMode="decimal"
                        value={l.credit}
                        onChange={(e) => update(i, "credit", e.target.value)}
                      />
                    </TD>
                    <TD>
                      <Button
                        size="xs"
                        disabled={lines.length < 3}
                        onClick={() =>
                          setLines((old) => old.filter((_, n) => n !== i))
                        }
                      >
                        Remove
                      </Button>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>
          <Button
            className="self-start"
            size="sm"
            icon="add"
            onClick={() => setLines((old) => [...old, blankLine(base)])}
          >
            Add line
          </Button>
          {lines.map(
            (l, i) =>
              (l.currency || base) !== base && (
                <div
                  key={i}
                  className="grid grid-cols-2 gap-3 border border-bd p-3"
                >
                  <Field
                    label={`Line ${i + 1} rate override (optional)`}
                    htmlFor={`rate-${i}`}
                    hint="Base currency per 1 foreign unit; blank uses historical rate table."
                  >
                    <Input
                      id={`rate-${i}`}
                      value={l.exchange_rate}
                      onChange={(e) =>
                        update(i, "exchange_rate", e.target.value)
                      }
                    />
                  </Field>
                  <Field label="Rate source / reason" htmlFor={`source-${i}`}>
                    <Input
                      id={`source-${i}`}
                      value={l.rate_source}
                      onChange={(e) => update(i, "rate_source", e.target.value)}
                    />
                  </Field>
                </div>
              ),
          )}
          <Field label="Reason / adjustment reference" htmlFor="journal-reason">
            <Textarea
              id="journal-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
          {lines.map((l, i) => {
            const revisions =
              taxes.data?.results.flatMap((t) =>
                t.is_active
                  ? t.revisions
                      .filter(
                        (r) =>
                          r.effective_date <= date &&
                          [r.input_account, r.output_account].includes(
                            Number(l.account_id),
                          ),
                      )
                      .map((r) => ({
                        value: String(r.id),
                        label: `${t.code} · ${r.percent}% · ${r.effective_date}`,
                      }))
                  : [],
              ) ?? [];
            return (
              revisions.length > 0 && (
                <Field
                  key={i}
                  label={`Line ${i + 1} tax revision (optional)`}
                  htmlFor={`tax-${i}`}
                >
                  <Select
                    id={`tax-${i}`}
                    value={l.tax_revision_id}
                    onChange={(e) =>
                      update(i, "tax_revision_id", e.target.value)
                    }
                  >
                    <option value="">No tax reference</option>
                    {revisions.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              )
            );
          })}
        </div>
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
