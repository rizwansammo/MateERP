import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AccountsPage } from "@/features/accounting/Accounts";
import { TransactionDrawer } from "@/features/accounting/Banking";
import { JournalEditor } from "@/features/accounting/Journals";
import { PeriodsPage } from "@/features/accounting/PeriodsTaxFx";
import { StatementsPage } from "@/features/accounting/Reports";
import { FinancialGate } from "@/features/accounting/shared";
import { amount, decimal, minor } from "@/features/accounting/money";
import type { Account } from "@/features/accounting/types";
import type { Bank } from "@/features/accounting/types";

import { makeUser, mockApi, renderWithAuth, viewerUser } from "./helpers";

const page = <T,>(results: T[]) => ({
  count: results.length,
  page: 1,
  page_size: 25,
  total_pages: 1,
  results,
});
const accounts: Account[] = [
  {
    id: 1,
    code: "1010",
    name: "Cash",
    account_type: "asset",
    subtype: "",
    parent_id: null,
    normal_side: "debit",
    description: "",
    is_active: true,
    is_postable: true,
    currency: "",
    control: "",
  },
  {
    id: 2,
    code: "3010",
    name: "Capital",
    account_type: "equity",
    subtype: "",
    parent_id: null,
    normal_side: "credit",
    description: "",
    is_active: true,
    is_postable: true,
    currency: "",
    control: "",
  },
];
const config = {
  base_currency: "BDT",
  enabled_currencies: ["BDT", "USD"],
  fiscal_year_start_month: 1,
};
const common = {
  "/auth/me/": makeUser(),
  "/accounting/config/": config,
  "/accounting/accounts/tree/": accounts,
  "/accounting/periods/": page([]),
};

describe("exact financial text", () => {
  it("preserves values larger than JavaScript safe integers", () => {
    const value = "999999999999999999.99";
    expect(decimal(minor(value, 2), 2)).toBe(value);
    expect(amount(value, "BDT")).toBe("BDT 999,999,999,999,999,999.99");
  });
  it("adds decimal strings exactly", () =>
    expect(decimal(minor("0.10") + minor("0.20"))).toBe("0.300000"));
  it("supports zero-minor-unit currencies and lakh grouping", () => {
    expect(amount("12345.000000", "JPY")).toBe("JPY 12,345");
    expect(amount("1234567.89", "BDT", "south_asian")).toBe("BDT 12,34,567.89");
  });
  it.each(["NaN", "Infinity", "1e3", "1.001", ""])(
    "rejects invalid or over-precise values %s",
    (value) => expect(() => minor(value, 2)).toThrow(),
  );
});

it("restricts financial screens before fetching business data", () => {
  mockApi({ "/auth/me/": makeUser({ permissions: [] }) });
  renderWithAuth(
    <FinancialGate>
      <span>Financial content</span>
    </FinancialGate>,
    makeUser({ permissions: [] }),
  );
  expect(screen.getByText("Access restricted")).toBeInTheDocument();
  expect(screen.queryByText("Financial content")).not.toBeInTheDocument();
});

it("lets viewers read the chart without mutation controls", async () => {
  mockApi({
    ...common,
    "/auth/me/": viewerUser,
    "/accounting/accounts/": page(accounts),
    "/accounting/ledger/": { rows: [] },
  });
  renderWithAuth(<AccountsPage />, viewerUser);
  expect(await screen.findByRole("link", { name: "Cash" })).toHaveAttribute(
    "href",
    "/banking/ledger/1",
  );
  expect(
    screen.queryByRole("button", { name: "New account" }),
  ).not.toBeInTheDocument();
});

it("saves journal amounts as decimal strings and displays server rejection", async () => {
  const calls = mockApi({
    ...common,
    "POST /accounting/journals/": [
      400,
      {
        error: {
          code: "validation_error",
          message: "Invalid",
          details: { lines: ["Base debits must equal base credits exactly."] },
          request_id: "test",
        },
      },
    ],
  });
  renderWithAuth(<JournalEditor onClose={() => {}} onSaved={() => {}} />);
  await screen.findAllByRole("option", { name: "1010 · Cash" });
  await userEvent.type(
    screen.getByRole("textbox", { name: "Narration" }),
    "Exact journal",
  );
  await userEvent.selectOptions(screen.getByLabelText("Line 1 account"), "1");
  await userEvent.selectOptions(screen.getByLabelText("Line 2 account"), "2");
  await userEvent.type(screen.getByLabelText("Line 1 debit"), "0.10");
  await userEvent.type(screen.getByLabelText("Line 2 credit"), "0.09");
  await userEvent.click(screen.getByRole("button", { name: "Post journal" }));
  expect(
    await screen.findByText("Base debits must equal base credits exactly."),
  ).toBeInTheDocument();
  const body = calls.find(
    (c) => c.method === "POST" && c.path === "/accounting/journals/",
  )!.body as { lines: { debit: string }[] };
  expect(body.lines[0]!.debit).toBe("0.10");
});

it("shows a balanced report with ledger drill-down and date filters", async () => {
  mockApi({
    ...common,
    "/accounting/reports/tb/": {
      report: "tb",
      base_currency: "BDT",
      rows: [
        {
          account_id: 1,
          code: "1010",
          name: "Cash",
          account_type: "asset",
          debit_balance: "10",
          credit_balance: "0",
        },
      ],
      total_debits: "10",
      total_credits: "10",
      difference: "0",
      balanced: true,
    },
  });
  renderWithAuth(<StatementsPage which="tb" />);
  expect(await screen.findByText(/Balanced · Difference/)).toBeInTheDocument();
  expect(screen.getByLabelText("From date")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Cash" })).toHaveAttribute(
    "href",
    expect.stringContaining("/banking/ledger/1?"),
  );
});

it("shows closed periods and keeps reopening hidden without period authority", async () => {
  mockApi({
    ...common,
    "/auth/me/": viewerUser,
    "/accounting/fiscal-years/": page([]),
    "/accounting/periods/": page([
      {
        id: 1,
        start: "2026-01-01",
        end: "2026-01-31",
        is_closed: true,
        entry_count: 0,
        revenue: "0",
        expenses: "0",
      },
    ]),
  });
  renderWithAuth(<PeriodsPage />, viewerUser);
  expect(await screen.findByText("Closed · locked")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Reopen" }),
  ).not.toBeInTheDocument();
});

it("requires a server preview and submits the reviewed fingerprint with exact amounts", async () => {
  const banks: Bank[] = [1, 2].map((id) => ({
    id,
    name: id === 1 ? "Cash" : "Bank",
    kind: id === 1 ? "cash" : "bank",
    institution: "",
    identifier: "",
    currency: "BDT",
    gl_account_id: id,
    is_active: true,
    balance: "100",
    book_value: "100",
  }));
  const calls = mockApi({
    ...common,
    "POST /banking/transactions/preview/": {
      lines: [],
      fx_difference: "0",
      base_currency: "BDT",
      quote_fingerprint: "a".repeat(64),
    },
    "POST /banking/transactions/": { id: "posted", status: "posted" },
  });
  const close = vi.fn();
  renderWithAuth(<TransactionDrawer banks={banks} onClose={close} />);
  await userEvent.selectOptions(
    screen.getByLabelText("Destination (transfers)"),
    "2",
  );
  await userEvent.type(
    screen.getByLabelText("Amount (primary account currency)"),
    "0.10",
  );
  await userEvent.type(screen.getByLabelText("Description"), "Exact transfer");
  await userEvent.click(
    screen.getByRole("button", { name: "Preview transaction" }),
  );
  await screen.findByText(/Preview ready/);
  expect(calls.filter((c) => c.path === "/banking/transactions/")).toHaveLength(
    0,
  );
  await userEvent.click(screen.getByRole("button", { name: "Confirm & post" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(
    calls.find((c) => c.path === "/banking/transactions/")!.body,
  ).toMatchObject({
    amount: "0.10",
    quote_fingerprint: "a".repeat(64),
    confirm_fx: true,
  });
  expect(close).toHaveBeenCalledOnce();
});
