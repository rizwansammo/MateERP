import { expect, test, type Page } from "@playwright/test";

import {
  apiPost,
  csrfHeaders,
  ensureUser,
  login,
  strongPassword,
} from "./support";

test.describe.configure({ mode: "serial" });
let cash: number,
  bank: number,
  cashGL: number,
  bankGL: number,
  capitalGL: number,
  expenseGL: number;
let openingId: string, unbalancedId: string;

async function loadAccounts(page: Page) {
  const rows = (await (
    await page.request.get("/api/v1/accounting/accounts/tree/")
  ).json()) as { id: number; code: string }[];
  const id = (code: string) => rows.find((a) => a.code === code)!.id;
  cashGL = id("1010");
  bankGL = id("1020");
  capitalGL = id("3010");
  expenseGL = id("6100");
}
async function journal(
  page: Page,
  description: string,
  debit: string,
  credit: string,
) {
  await page.goto("/banking/journals");
  await page.getByRole("button", { name: "New journal", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "New journal entry" });
  await dialog.getByLabel("Journal date", { exact: true }).fill("2026-10-10");
  await dialog.getByLabel("Narration").fill(description);
  await dialog.getByLabel("Line 1 account").selectOption(String(cashGL));
  await dialog.getByLabel("Line 2 account").selectOption(String(capitalGL));
  await dialog.getByLabel("Line 1 debit").fill(debit);
  await dialog.getByLabel("Line 2 credit").fill(credit);
  return dialog;
}

test("A — setup chart, fiscal year and real bank accounts through the interface", async ({
  page,
}) => {
  const company = await page.request.get("/api/v1/company/");
  if (!(await company.json()).display_name) {
    expect(
      (
        await apiPost(page.request, page.context(), "/api/v1/company/", {
          display_name: "NetaMate",
          base_currency: "BDT",
          time_zone: "Asia/Dhaka",
          fiscal_year_start_month: 1,
        })
      ).status(),
    ).toBe(201);
  }
  await page.goto("/banking/coa");
  await page.getByRole("button", { name: "Set up starter chart" }).click();
  await page.getByRole("button", { name: "Create chart", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Cash", exact: true }),
  ).toBeVisible();
  await loadAccounts(page);
  await page.goto("/banking/periods");
  await page.getByRole("button", { name: "New fiscal year" }).click();
  await page
    .getByLabel("Fiscal year start", { exact: true })
    .fill("2026-01-01");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Save", exact: true })
    .click();
  await expect(
    page.getByRole("cell", {
      name: "2026-10 2026-10-01 — 2026-10-31",
      exact: true,
    }),
  ).toBeVisible();
  for (const [name, kind, gl] of [
    ["Petty cash", "cash", cashGL],
    ["Operating bank", "bank", bankGL],
  ] as const) {
    await page.goto("/banking/accounts");
    await page.getByRole("button", { name: "New bank account" }).click();
    const d = page.getByRole("dialog");
    await d.getByLabel("Account name").fill(name);
    await d.getByLabel("Type", { exact: true }).selectOption(kind);
    await d.getByLabel("Linked GL account").selectOption(String(gl));
    await d.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  }
  const rows = await (
    await page.request.get("/api/v1/banking/accounts/")
  ).json();
  cash = rows.results.find((b: { name: string }) => b.name === "Petty cash").id;
  bank = rows.results.find(
    (b: { name: string }) => b.name === "Operating bank",
  ).id;
});

test("B, H, I — balanced opening journal posts and locks financial identity", async ({
  page,
}) => {
  await page.goto("/banking/journals");
  await page
    .getByRole("button", { name: "Opening balances", exact: true })
    .click();
  const d = page.getByRole("dialog", { name: "Opening balances" });
  await d.getByLabel("Journal date", { exact: true }).fill("2026-10-01");
  await d.getByLabel("Narration").fill("Migration opening balance");
  await d.getByLabel("Line 1 account").selectOption(String(cashGL));
  await d.getByLabel("Line 2 account").selectOption(String(capitalGL));
  await d.getByLabel("Line 1 debit").fill("1000.00");
  await d.getByLabel("Line 2 credit").fill("1000.00");
  await d.getByRole("button", { name: "Post journal", exact: true }).click();
  await expect(page).toHaveURL(/\/banking\/journals\/[a-f0-9-]+/);
  openingId = page.url().split("/").pop()!;
  await expect(page.getByText("posted", { exact: true })).toBeVisible();
  const changed = await page.request.patch("/api/v1/company/", {
    headers: await csrfHeaders(page.context()),
    data: { base_currency: "USD" },
  });
  expect(changed.status()).toBe(409);
  const duplicate = await apiPost(
    page.request,
    page.context(),
    "/api/v1/accounting/opening-balances/",
    {
      posting_date: "2026-10-01",
      description: "Duplicate opening",
      lines: [
        { account_id: cashGL, debit: "1" },
        { account_id: capitalGL, credit: "1" },
      ],
    },
  );
  expect(duplicate.status()).toBe(409);
});

test("C, D — unbalanced journals fail; posted content cannot be changed", async ({
  page,
}) => {
  const d = await journal(page, "Rejected unbalanced entry", "10.00", "9.00");
  await d.getByRole("button", { name: "Post journal", exact: true }).click();
  await expect(d.getByRole("alert")).toContainText(
    "Base debits must equal base credits",
  );
  const rows = await (
    await page.request.get("/api/v1/accounting/journals/?search=Rejected")
  ).json();
  unbalancedId = rows.results[0].id;
  expect(rows.results[0].status).toBe("draft");
  const attempt = await page.request.patch(
    `/api/v1/accounting/journals/${openingId}/`,
    {
      headers: await csrfHeaders(page.context()),
      data: {
        revision: 1,
        posting_date: "2026-10-01",
        description: "Tampered",
        lines: [
          { account_id: cashGL, debit: "1" },
          { account_id: capitalGL, credit: "1" },
        ],
      },
    },
  );
  expect(attempt.status()).toBe(409);
});

test("F, J — bank transfer posts once, including concurrent identical retries", async ({
  page,
}) => {
  await page.goto("/banking/transactions");
  await page
    .getByRole("button", { name: "Record transaction", exact: true })
    .click();
  const d = page.getByRole("dialog");
  await d.getByLabel("From / primary account").selectOption(String(cash));
  await d.getByLabel("Destination (transfers)").selectOption(String(bank));
  await d.getByLabel("Posting date", { exact: true }).fill("2026-10-10");
  await d
    .getByLabel("Amount (primary account currency)", { exact: true })
    .fill("250.00");
  await d
    .getByLabel("Description", { exact: true })
    .fill("Internal bank transfer");
  await d.getByRole("button", { name: "Preview transaction" }).click();
  await expect(d.getByText(/Preview ready/)).toBeVisible();
  await d.getByRole("button", { name: "Confirm & post" }).click();
  await expect(d).toHaveCount(0);
  const rows = await (
    await page.request.get("/api/v1/accounting/journals/?search=Internal")
  ).json();
  expect(rows.results[0].status).toBe("posted");
  const data = {
    posting_key: "browser-concurrent-transfer",
    kind: "transfer",
    bank_account_id: cash,
    destination_id: bank,
    amount: "1.00",
    posting_date: "2026-10-10",
    description: "Concurrent retry check",
  };
  const responses = await Promise.all([
    apiPost(
      page.request,
      page.context(),
      "/api/v1/banking/transactions/",
      data,
    ),
    apiPost(
      page.request,
      page.context(),
      "/api/v1/banking/transactions/",
      data,
    ),
  ]);
  expect(responses.map((r) => r.status())).toEqual([201, 201]);
  const ids = await Promise.all(
    responses.map(async (r) => (await r.json()).id),
  );
  expect(ids[0]).toBe(ids[1]);
  const pnl = await (
    await page.request.get(
      "/api/v1/accounting/reports/pnl/?from=2026-01-01&to=2026-12-31",
    )
  ).json();
  expect(pnl.net_profit).toMatch(/^0(?:\.0+)?$/);
});

test("K — real bank statement matches ledger and completes", async ({
  page,
}) => {
  await page.goto("/banking/reconciliation");
  await page.getByRole("button", { name: "New statement" }).click();
  const d = page.getByRole("dialog");
  await d
    .getByLabel("Bank account", { exact: true })
    .selectOption(String(bank));
  await d
    .getByLabel("Statement reference")
    .fill("October acceptance statement");
  await d.getByLabel("From date", { exact: true }).fill("2026-10-01");
  await d.getByLabel("To date", { exact: true }).fill("2026-10-31");
  await d.getByLabel("Closing balance").fill("251.00");
  await d.getByLabel("Statement line 1 date").fill("2026-10-10");
  await d.getByLabel("Statement line 1 description").fill("Grouped transfers");
  await d.getByLabel("Statement line 1 amount").fill("251.00");
  await d.getByRole("button", { name: "Save", exact: true }).click();
  await expect(d).toHaveCount(0);
  await page.getByLabel("Select statement Grouped transfers").check();
  const checks = page.getByRole("checkbox", { name: /Select ledger/ });
  expect(await checks.count()).toBe(2);
  await checks.nth(0).check();
  await checks.nth(1).check();
  await page.getByRole("button", { name: "Match selected group" }).click();
  await expect(page.getByText("Matched", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Complete reconciliation", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Complete", exact: true })
    .click();
  await expect(page.getByText("Complete", { exact: true })).toBeVisible();
  expect(
    (
      await apiPost(
        page.request,
        page.context(),
        "/api/v1/banking/reconciliations/1/match/",
        { statement_ids: [1], ledger_ids: [1] },
      )
    ).status(),
  ).toBe(409);
});

test("E, G — reversal preserves original; closed periods reject posting and require a reason to reopen", async ({
  page,
}) => {
  const response = await apiPost(
    page.request,
    page.context(),
    "/api/v1/accounting/journals/",
    {
      posting_date: "2026-10-10",
      description: "Reversible journal",
      lines: [
        { account_id: cashGL, debit: "5" },
        { account_id: capitalGL, credit: "5" },
      ],
    },
  );
  const j = await response.json();
  await apiPost(
    page.request,
    page.context(),
    `/api/v1/accounting/journals/${j.id}/post/`,
    { posting_key: "reversible-browser-post" },
  );
  await page.goto(`/banking/journals/${j.id}`);
  await page.getByRole("button", { name: "Reverse", exact: true }).click();
  const d = page.getByRole("dialog");
  await d.getByLabel("Reversal date").fill("2026-10-11");
  await d.getByLabel("Reason", { exact: true }).fill("Acceptance correction");
  await d.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(/Reversal of/)).toBeVisible();
  await page.goto("/banking/periods");
  const row = page
    .getByRole("row")
    .filter({ hasText: "2026-10-01 — 2026-10-31" });
  await row.getByRole("button", { name: "Close", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Close period" })
    .click();
  await expect(row.getByText("Closed · locked", { exact: true })).toBeVisible();
  const rejected = await apiPost(
    page.request,
    page.context(),
    `/api/v1/accounting/journals/${unbalancedId}/post/`,
    { posting_key: "closed-period-test" },
  );
  expect(rejected.status()).toBe(400);
  const body = await rejected.json();
  expect(JSON.stringify(body)).toContain("open accounting period");
  await row.getByRole("button", { name: "Reopen", exact: true }).click();
  await page.getByLabel("Reason", { exact: true }).fill("Acceptance review");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Reopen period" })
    .click();
  await expect(row.getByText("Open", { exact: true })).toBeVisible();
});

test("L, M, O — FX snapshots, financial reports and separate-person approval", async ({
  page,
  browser,
}) => {
  await page.goto("/settings/currency");
  await page.request.patch("/api/v1/settings/business/", {
    headers: await csrfHeaders(page.context()),
    data: { enabled_currencies: ["BDT", "USD"] },
  });
  await page.reload();
  await page.getByRole("button", { name: "Add exchange rate" }).click();
  const rateDialog = page.getByRole("dialog");
  await rateDialog.getByLabel("Currency", { exact: true }).selectOption("USD");
  await rateDialog.getByLabel("Effective from").fill("2026-10-01");
  await rateDialog.getByLabel("Base currency per 1 unit").fill("120");
  await rateDialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(rateDialog).toHaveCount(0);
  const accounts = await (
    await page.request.get("/api/v1/accounting/accounts/tree/")
  ).json();
  const receivable = accounts.find(
    (a: { code: string }) => a.code === "1100",
  ).id;
  const foreign = await apiPost(
    page.request,
    page.context(),
    "/api/v1/accounting/journals/",
    {
      posting_date: "2026-10-12",
      description: "Historical FX snapshot",
      lines: [
        { account_id: receivable, currency: "USD", debit: "10" },
        { account_id: capitalGL, credit: "1200" },
      ],
    },
  );
  const foreignJournal = await foreign.json();
  expect(
    (
      await apiPost(
        page.request,
        page.context(),
        `/api/v1/accounting/journals/${foreignJournal.id}/post/`,
        { posting_key: "fx-snapshot-browser" },
      )
    ).status(),
  ).toBe(200);
  expect(
    (
      await apiPost(
        page.request,
        page.context(),
        "/api/v1/accounting/exchange-rates/",
        {
          currency: "USD",
          effective_date: "2026-10-01",
          value: "130",
          source: "Later revision",
        },
      )
    ).status(),
  ).toBe(201);
  const preserved = await (
    await page.request.get(`/api/v1/accounting/journals/${foreignJournal.id}/`)
  ).json();
  expect(preserved.lines[0].exchange_rate).toBe("120.000000000000");
  await page.goto("/banking/journals");
  await page.request.patch(
    "/api/v1/approvals/policies/financial_adjustments/",
    {
      headers: await csrfHeaders(page.context()),
      data: {
        is_required: true,
        is_active: true,
        amount_threshold: "0",
        allow_self_approval: false,
      },
    },
  );
  const response = await apiPost(
    page.request,
    page.context(),
    "/api/v1/accounting/journals/",
    {
      posting_date: "2026-10-12",
      description: "Approved expense adjustment",
      lines: [
        { account_id: expenseGL, debit: "40" },
        { account_id: cashGL, credit: "40" },
      ],
    },
  );
  const journal = await response.json();
  const submitted = await apiPost(
    page.request,
    page.context(),
    `/api/v1/accounting/journals/${journal.id}/post/`,
    { posting_key: "approval-browser-test" },
  );
  const pending = await submitted.json();
  expect(pending.status).toBe("pending_approval");
  expect(
    (
      await apiPost(
        page.request,
        page.context(),
        `/api/v1/approvals/requests/${pending.journal.approval_id}/approve/`,
        {},
      )
    ).status(),
  ).toBe(403);
  const password = strongPassword();
  ensureUser("e2e-accounting-approver", "administrator", password);
  const ctx = await browser.newContext({
    storageState: { cookies: [], origins: [] },
  });
  const approver = await ctx.newPage();
  await login(approver, "e2e-accounting-approver", password);
  await expect(approver).toHaveURL(/dashboard/);
  await approver.goto("/settings/approvals");
  const row = approver
    .getByRole("row")
    .filter({ hasText: "Approved expense adjustment" });
  await expect(
    row.getByRole("link", { name: "Review journal lines" }),
  ).toBeVisible();
  await row.getByRole("button", { name: "Approve", exact: true }).click();
  await approver
    .getByRole("dialog")
    .getByRole("button", { name: "Approve", exact: true })
    .click();
  await expect(row).toHaveCount(0);
  expect(
    (
      await (
        await approver.request.get(`/api/v1/accounting/journals/${journal.id}/`)
      ).json()
    ).status,
  ).toBe("posted");
  await ctx.close();
  const tb = await (
    await page.request.get(
      "/api/v1/accounting/reports/tb/?from=2026-01-01&to=2026-12-31",
    )
  ).json();
  expect(tb.balanced).toBe(true);
  const pnl = await (
    await page.request.get(
      "/api/v1/accounting/reports/pnl/?from=2026-01-01&to=2026-12-31",
    )
  ).json();
  expect(pnl.net_profit).toBe("-40.000000");
  const bs = await (
    await page.request.get(
      "/api/v1/accounting/reports/bs/?from=2026-01-01&to=2026-12-31",
    )
  ).json();
  expect(bs.balanced).toBe(true);
  await page.goto("/banking/statements/tb");
  await expect(page.getByText(/Balanced · Difference/)).toBeVisible();
  await page.request.patch(
    "/api/v1/approvals/policies/financial_adjustments/",
    {
      headers: await csrfHeaders(page.context()),
      data: { is_required: false },
    },
  );
});

test("N, P, Q — viewer restrictions and prototype shell in both themes and mobile", async ({
  page,
  browser,
}) => {
  const noCsrf = await page.request.post("/api/v1/accounting/journals/", {
    data: {},
  });
  expect(noCsrf.status()).toBe(403);
  expect((await noCsrf.json()).error.code).toBe("csrf_failed");
  const password = strongPassword();
  ensureUser("e2e-finance-viewer", "viewer", password);
  const ctx = await browser.newContext({
    storageState: { cookies: [], origins: [] },
  });
  const viewer = await ctx.newPage();
  await login(viewer, "e2e-finance-viewer", password);
  await expect(viewer).toHaveURL(/dashboard/);
  await viewer.goto("/banking/coa");
  await expect(
    viewer.getByRole("link", { name: "Cash", exact: true }),
  ).toBeVisible();
  await expect(viewer.getByRole("button", { name: "New account" })).toHaveCount(
    0,
  );
  expect(
    (
      await apiPost(viewer.request, ctx, "/api/v1/accounting/journals/", {})
    ).status(),
  ).toBe(403);
  await ctx.close();
  await page.goto("/banking/coa");
  if (await page.getByRole("button", { name: "Expand sidebar" }).isVisible())
    await page.getByRole("button", { name: "Expand sidebar" }).click();
  if (
    await page.getByRole("button", { name: "Switch to light mode" }).isVisible()
  )
    await page.getByRole("button", { name: "Switch to light mode" }).click();
  await expect(page.getByTestId("sidebar")).toHaveCSS("width", "264px");
  await expect(page.getByRole("banner")).toHaveCSS("height", "56px");
  await page.goto('/banking/overview');
  await expect(page.getByRole('img', { name: 'Month-end cash balance chart' })).toBeVisible();
  await page.screenshot({ path: 'test-results/accounting-overview.png', animations: 'disabled' });
  await page.goto(`/banking/journals/${openingId}`);
  await expect(page.getByText('posted', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/accounting-journal.png', animations: 'disabled' });
  await page.goto('/banking/reconciliation');
  await expect(page.getByText('Grouped transfers', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/accounting-reconciliation.png', animations: 'disabled' });
  await page.goto('/banking/statements/tb');
  await expect(page.getByText(/Balanced · Difference/)).toBeVisible();
  await page.screenshot({ path: 'test-results/accounting-trial-balance.png', animations: 'disabled' });
  await page.goto('/banking/coa');
  await expect(page.getByRole('link', { name: 'Cash', exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/accounting-light.png" });
  await page.getByRole("button", { name: "Switch to dark mode" }).click();
  await page.screenshot({ path: "test-results/accounting-dark.png" });
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.getByTestId("sidebar")).toHaveCSS("width", "64px");
  await page.screenshot({ path: "test-results/accounting-compact.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("sidebar")).not.toBeInViewport();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByTestId("sidebar")).toBeInViewport();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("sidebar")).not.toBeInViewport();
  await page.screenshot({
    path: "test-results/accounting-mobile.png",
    animations: "disabled",
  });
  // Preserve the shared administrator's baseline for subsequent shell regressions.
  await page.setViewportSize({ width: 1440, height: 900 });
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/v1/auth/me/") &&
        r.request().method() === "PATCH" &&
        r.status() === 200,
    ),
    page.getByRole("button", { name: "Expand sidebar" }).click(),
  ]);
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/v1/auth/me/") &&
        r.request().method() === "PATCH" &&
        r.status() === 200,
    ),
    page.getByRole("button", { name: "Switch to light mode" }).click(),
  ]);
});
