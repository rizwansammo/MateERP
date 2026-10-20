"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Input, Select } from "@/components/ui/Input";
import { Panel, PanelHeader } from "@/components/ui/Panel";
import { StatGrid } from "@/components/ui/StatGrid";
import { Table, THead, TBody, TH, TR, TD } from "@/components/ui/Table";
import { toast } from "@/components/ui/Toast";
import { api, errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";

import { TransactionDrawer } from "./Banking";
import { minor } from "./money";
import {
  EntityDrawer,
  type FormField,
  JournalLink,
  type Page,
  QueryState,
  Screen,
  refreshFinance,
  today,
  useFinance,
  useMoney,
} from "./shared";
import type { Bank, Reconciliation } from "./types";

export function ReconciliationPage() {
  const amount = useMoney();
  const { can } = useAuth();
  const banks = useFinance<Page<Bank>>("/banking/accounts/?page_size=100");
  const [bank, setBank] = useState("");
  const [selected, setSelected] = useState("");
  const [create, setCreate] = useState(false);
  const list = useFinance<Page<Reconciliation>>(
    `/banking/reconciliations/?bank=${bank}&page_size=100`,
  );
  const selectedId =
    selected || (list.data?.results[0] ? String(list.data.results[0].id) : "");
  const rec = useFinance<Reconciliation>(
    selectedId ? `/banking/reconciliations/${selectedId}/` : null,
  );
  const [ss, setSs] = useState<number[]>([]);
  const [ll, setLl] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [complete, setComplete] = useState(false);
  const [tx, setTx] = useState<Record<string, string> | null>(null);
  const run = async (url: string, data?: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await api.post(url, data);
      setSs([]);
      setLl([]);
      refreshFinance();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const toggle = (ids: number[], id: number) =>
    ids.includes(id) ? ids.filter((n) => n !== id) : [...ids, id];
  const r = rec.data;
  return (
    <Screen
      title="Bank reconciliation"
      description="Match manually entered bank statements against posted ledger lines. Review timing differences and complete a balanced reconciliation."
      actions={
        can("accounting.manage") && (
          <Button variant="primary" icon="add" onClick={() => setCreate(true)}>
            New statement
          </Button>
        )
      }
    >
      <div className="flex flex-wrap gap-3">
        <span className="w-[240px]">
          <Select
            aria-label="Bank account"
            value={bank}
            onChange={(e) => {
              setBank(e.target.value);
              setSelected("");
            }}
          >
            <option value="">All bank accounts</option>
            {banks.data?.results
              .filter((b) => b.kind === "bank")
              .map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} · {b.currency}
                </option>
              ))}
          </Select>
        </span>
        <span className="w-[320px]">
          <Select
            aria-label="Statement"
            value={selectedId}
            onChange={(e) => {
              setSelected(e.target.value);
              setSs([]);
              setLl([]);
            }}
          >
            <option value="">Select statement</option>
            {list.data?.results.map((x) => (
              <option key={x.id} value={x.id}>
                {x.reference} · {x.start} — {x.end}
              </option>
            ))}
          </Select>
        </span>
      </div>
      <QueryState
        loading={list.loading || (!!selectedId && rec.loading)}
        error={list.error || rec.error}
      />
      {!selectedId && !list.loading && (
        <Banner tone="info">
          No bank statements yet. Add a bank account, then enter its statement
          and balances. Statement import does not create ledger entries.
        </Banner>
      )}
      {error && <Banner tone="err">{error}</Banner>}
      {r && (
        <>
          <StatGrid
            minWidth={180}
            stats={[
              {
                label: "Statement lines",
                value: String(r.lines.length),
                accentBar: true,
              },
              {
                label: "Unmatched statement",
                value: String(r.summary.unmatched_statement),
                tone: r.summary.unmatched_statement ? "warn" : "ok",
              },
              {
                label: "Unmatched ledger",
                value: String(r.summary.unmatched_ledger),
                accentBar: true,
              },
              {
                label: "Statement closing",
                value: amount(r.summary.statement_balance, r.currency),
                accentBar: true,
              },
              {
                label: "Ledger closing",
                value: amount(r.summary.ledger_balance, r.currency),
                accentBar: true,
              },
              {
                label: "Difference after timing items",
                value: amount(r.summary.difference, r.currency),
                tone: minor(r.summary.difference) ? "err" : "ok",
              },
            ]}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={r.is_complete ? "ok" : "warn"}>
              {r.is_complete ? "Complete" : "Open"}
            </Badge>
            {can("accounting.manage") && !r.is_complete && (
              <>
                <Button
                  size="sm"
                  disabled={busy}
                  onClick={() =>
                    void run(`/banking/reconciliations/${r.id}/auto-match/`)
                  }
                >
                  Auto-match exact amounts
                </Button>
                <Button
                  size="sm"
                  disabled={busy || !ss.length || !ll.length}
                  onClick={() =>
                    void run(`/banking/reconciliations/${r.id}/match/`, {
                      statement_ids: ss,
                      ledger_ids: ll,
                    })
                  }
                >
                  Match selected group
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  disabled={busy}
                  onClick={() => setComplete(true)}
                >
                  Complete reconciliation
                </Button>
              </>
            )}
            {can("accounting.periods.manage") && r.is_complete && (
              <Button size="sm" onClick={() => setComplete(true)}>
                Reopen reconciliation
              </Button>
            )}
          </div>
          <Panel>
            <PanelHeader
              title="Bank statement"
              subtitle={`${r.bank_account_name} · ${r.start} — ${r.end} · ${r.currency}`}
            />
            <Table>
              <THead>
                <TR>
                  <TH>Select</TH>
                  <TH>Date</TH>
                  <TH>Statement description</TH>
                  <TH align="right">Amount</TH>
                  <TH>Status / match</TH>
                  <TH>Actions</TH>
                </TR>
              </THead>
              <TBody>
                {r.lines.map((s) => {
                  const candidates = r.ledger.filter(
                    (l) => minor(l.debit) - minor(l.credit) === minor(s.amount),
                  );
                  return (
                    <TR key={s.id}>
                      <TD>
                        <input
                          type="checkbox"
                          aria-label={`Select statement ${s.description}`}
                          disabled={
                            r.is_complete ||
                            !!s.match_group_id ||
                            !can("accounting.manage")
                          }
                          checked={ss.includes(s.id)}
                          onChange={() => setSs(toggle(ss, s.id))}
                        />
                      </TD>
                      <TD>{s.date}</TD>
                      <TD>
                        {s.description}
                        <div className="text-[11.5px] text-tx3">
                          {s.reference}
                        </div>
                      </TD>
                      <TD align="right">{amount(s.amount, r.currency)}</TD>
                      <TD>
                        <Badge tone={s.match_group_id ? "ok" : "warn"}>
                          {s.match_group_id ? "Matched" : "Unmatched"}
                        </Badge>
                        {!s.match_group_id && (
                          <div className="text-[11.5px] text-tx3">
                            {candidates.length} exact amount candidates
                          </div>
                        )}
                      </TD>
                      <TD>
                        {can("accounting.manage") &&
                          !r.is_complete &&
                          (s.match_group_id ? (
                            <Button
                              size="xs"
                              disabled={busy}
                              onClick={() =>
                                void run(
                                  `/banking/reconciliations/${r.id}/unmatch/`,
                                  { match_group_id: s.match_group_id },
                                )
                              }
                            >
                              Unmatch
                            </Button>
                          ) : (
                            <div className="flex flex-wrap gap-1">
                              {candidates.length === 1 && (
                                <Button
                                  size="xs"
                                  disabled={busy}
                                  onClick={() =>
                                    void run(
                                      `/banking/reconciliations/${r.id}/match/`,
                                      {
                                        statement_ids: [s.id],
                                        ledger_ids: [candidates[0]!.id],
                                      },
                                    )
                                  }
                                >
                                  Match {candidates[0]!.number}
                                </Button>
                              )}
                              <Button
                                size="xs"
                                onClick={() =>
                                  setTx({
                                    kind:
                                      minor(s.amount) > 0n
                                        ? "interest"
                                        : "charge",
                                    bank_account_id: String(r.bank_account_id),
                                    posting_date: s.date,
                                    amount: s.amount.replace("-", ""),
                                    description: s.description,
                                  })
                                }
                              >
                                Create entry
                              </Button>
                            </div>
                          ))}
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          </Panel>
          <Panel>
            <PanelHeader
              title="Ledger entries not yet on the statement"
              subtitle="Select one or more lines to form an exact group. Outstanding lines may be timing differences."
            />
            <Table>
              <THead>
                <TR>
                  <TH>Select</TH>
                  <TH>Date</TH>
                  <TH>Reference</TH>
                  <TH>Description</TH>
                  <TH align="right">Money in</TH>
                  <TH align="right">Money out</TH>
                </TR>
              </THead>
              <TBody>
                {r.ledger.length === 0 && (
                  <TR>
                    <TD colSpan={6} className="text-center text-tx3">
                      Everything is reconciled.
                    </TD>
                  </TR>
                )}
                {r.ledger.map((l) => (
                  <TR key={l.id}>
                    <TD>
                      <input
                        type="checkbox"
                        aria-label={`Select ledger ${l.number}`}
                        checked={ll.includes(l.id)}
                        disabled={r.is_complete || !can("accounting.manage")}
                        onChange={() => setLl(toggle(ll, l.id))}
                      />
                    </TD>
                    <TD>{l.date}</TD>
                    <TD>
                      <JournalLink id={l.journal_id}>{l.number}</JournalLink>
                    </TD>
                    <TD>{l.description}</TD>
                    <TD align="right">{amount(l.debit, l.currency)}</TD>
                    <TD align="right">{amount(l.credit, l.currency)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Panel>
          <Banner tone="info">
            Statement closing {amount(r.closing_balance, r.currency)} +
            outstanding net {amount(r.summary.outstanding_net, r.currency)} =
            ledger closing {amount(r.summary.ledger_balance, r.currency)}.
            Statement-only charges or interest require an explicitly reviewed
            posting before matching.
          </Banner>
          <ConfirmDialog
            open={complete}
            title={
              r.is_complete
                ? "Reopen reconciliation?"
                : "Complete reconciliation?"
            }
            confirmLabel={r.is_complete ? "Reopen" : "Complete"}
            reason={r.is_complete ? "required" : undefined}
            onCancel={() => setComplete(false)}
            onConfirm={async (reason) => {
              await api.post(
                `/banking/reconciliations/${r.id}/${r.is_complete ? "reopen" : "complete"}/`,
                { reason },
              );
              refreshFinance();
              setComplete(false);
              toast(
                r.is_complete
                  ? "Reconciliation reopened"
                  : "Reconciliation completed",
              );
            }}
          >
            <p>
              {r.is_complete
                ? "Your reason is retained with the earlier completion evidence."
                : "Completion freezes the matches. All statement lines must be resolved and balances must reconcile exactly."}
            </p>
          </ConfirmDialog>
        </>
      )}
      {create && (
        <StatementDrawer
          banks={banks.data?.results ?? []}
          onClose={() => setCreate(false)}
          onSaved={(id) => setSelected(String(id))}
        />
      )}
      {tx && (
        <TransactionDrawer
          banks={banks.data?.results ?? []}
          initial={tx}
          onClose={() => setTx(null)}
        />
      )}
    </Screen>
  );
}
function StatementDrawer({
  banks,
  onClose,
  onSaved,
}: {
  banks: Bank[];
  onClose: () => void;
  onSaved: (id: number) => void;
}) {
  const [lines, setLines] = useState([
    { date: today(), description: "", amount: "", reference: "" },
  ]);
  const [initialLines] = useState(() => JSON.stringify(lines));
  const fields: FormField[] = [
    {
      key: "bank_account_id",
      label: "Bank account",
      type: "id",
      options: [
        { value: "", label: "Select bank" },
        ...banks
          .filter((b) => b.kind === "bank")
          .map((b) => ({
            value: String(b.id),
            label: `${b.name} (${b.currency})`,
          })),
      ],
    },
    { key: "reference", label: "Statement reference", required: true },
    { key: "start", label: "From date", type: "date" },
    { key: "end", label: "To date", type: "date" },
    { key: "opening_balance", label: "Opening balance", type: "amount" },
    { key: "closing_balance", label: "Closing balance", type: "amount" },
  ];
  return (
    <EntityDrawer
      title="New bank statement"
      extraDirty={JSON.stringify(lines) !== initialLines}
      width={900}
      fields={fields}
      initial={{
        bank_account_id: "",
        reference: "",
        start: `${today().slice(0, 7)}-01`,
        end: today(),
        opening_balance: "0",
        closing_balance: "",
      }}
      onClose={onClose}
      onSave={async (data) => {
        const r = await api.post<Reconciliation>("/banking/reconciliations/", {
          ...data,
          lines,
        });
        onSaved(r.id);
      }}
    >
      <div className="mt-5 flex flex-col gap-3">
        <Banner tone="info">
          Enter signed amounts: deposits positive, withdrawals negative. Opening
          plus lines must equal closing. No journals are created here.
        </Banner>
        <Table>
          <THead>
            <TR>
              <TH>Date</TH>
              <TH>Description</TH>
              <TH>Reference</TH>
              <TH align="right">Signed amount</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {lines.map((l, i) => (
              <TR key={i}>
                {(["date", "description", "reference", "amount"] as const).map(
                  (f) => (
                    <TD key={f}>
                      <Input
                        aria-label={`Statement line ${i + 1} ${f}`}
                        type={f === "date" ? "date" : "text"}
                        inputMode={f === "amount" ? "decimal" : undefined}
                        value={l[f]}
                        onChange={(e) =>
                          setLines((old) =>
                            old.map((x, n) =>
                              n === i ? { ...x, [f]: e.target.value } : x,
                            ),
                          )
                        }
                      />
                    </TD>
                  ),
                )}
                <TD>
                  <Button
                    size="xs"
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
        <Button
          size="sm"
          className="self-start"
          onClick={() =>
            setLines((old) => [
              ...old,
              { date: today(), description: "", reference: "", amount: "" },
            ])
          }
        >
          Add statement line
        </Button>
      </div>
    </EntityDrawer>
  );
}
