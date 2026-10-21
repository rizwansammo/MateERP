# Phase 5 — Founder Finance and Ownership

Release 0.5.0. Phase 5 is implemented and verified locally. Work remains uncommitted on `main`; no push, deployment or Phase 6 development is authorized.

## Delivered features and files

| Area | Implementation |
|---|---|
| Participants | `company.FinancialParty`: founders, shareholders, organizations/individuals, participation dates, optional authorized ERP-account links |
| Company finance | `apps/founders/services/corporate.py`: independently verified receipts, principal agreements/drawdowns, founder-paid purchasing expenses, existing AP settlement, partial reimbursements/repayments, explicit reclassification/reassignment and source-owned reversals |
| Personal sharing | `services/sharing.py`: effective equal/custom/provisional/formal policies, frozen allocations, exact largest-remainder rounding, partial transfers, independent party confirmations, authorized external attestations, disputes and confirmed returns |
| Recovery integrity | Original recovery identity survives split/reclassified liabilities. Payout checks aggregate the entire history; overlap blocks until an actual return or explicit independently verified/audited corporate resolution. No automatic GL liability reduction |
| Planning | `services/planning.py`: monthly/12-month immutable forecast revisions, recurrence/actual-occurrence deduplication, selected one-off obligations, native amounts and explicit FX estimates, requests/promises, actual verified contribution progress, partial company-cash coverage |
| Annual reserves | Specific renewal cycles, exact monthly targets, actual cash-backed designations, partial consumption tied to real payments, audited release and retained-funds rollover, shortfall/surplus disclosure |
| Ownership | `apps/ownership/services/register.py`: provisional agreements/amendments, configured share classes, existing-register setup, atomic transfer groups, issuance/dilution, frozen before/after snapshots, participant consent, independent quorum, documented confirmation and historical as-of views |
| Capital | Formal units/nominal values, recorded paid-in funding, premium, other equity and unpaid subscription commitments remain separate. Commitments never invent cash or receivables |
| Evidence and reports | Existing validated private storage/access registry; founder/personal/ownership purposes; paginated corporate statements/CSV and separate personal balances; general journal responses mask founder identity dimensions without altering totals |
| UI | New `features/founders/` and `features/ownership/`; real `/founder/[[...path]]` and `/ownership/[[...path]]` routes; existing design primitives, drawers/previews, source evidence, approval states, filters and responsive shell |
| Foundation integration | Stable permissions, frozen distinct approval votes, owning-domain rejection/withdrawal, protected account purposes, AP/vendor statement integration and immutable founder-owned purchasing sources |

The existing Django/Next/PostgreSQL modular monolith, session/CSRF proxy, private storage and Docker/native Windows arrangement are retained. No new service, worker, scheduler, identity provider or dependency upgrade was required.

Contribution progress also compares fulfilled source identities with the saved base-currency estimate. Actual costs and rates come from posted purchasing records; unfulfilled estimates are never shown as a favorable variance. Price changes and FX can both contribute to the disclosed cost variance.

## Financial examples and mandatory clarifications

- A verified BDT 20,000 loan receipt debits company bank and credits principal liability. A BDT 5,000 repayment removes only 5,000 principal; it is not expense or revenue.
- A founder-paid BDT 20,000 business expense produces one purchasing cost and one founder obligation. BDT 5,000 reimbursement leaves exactly 15,000 outstanding; settling an already posted vendor bill debits historical AP without repeating its expense.
- A BDT 10,000 confirmed personal payment against that cost leaves the full company liability intact. A proposed BDT 20,000 company reimbursement is blocked for duplicate recovery. Actual confirmed personal returns or an independently verified liability reassignment plus an audited authorized resolution can resolve the overlap. Splitting the liability into payable/loan portions does not reset its recovery limit.
- Monthly VPS 4,000 + subscription 2,000 yields 6,000; a December renewal of 1,200 yields 7,200. Equal targets are 3,000 / 3,000 and 3,600 / 3,600. Effective 40:40:20 targets become 2,400 / 2,400 / 1,200 and 2,880 / 2,880 / 1,440 without rewriting prior saved plans.
- Annual 1,200 over twelve months targets 100/month. With 1,100 actually retained and available, the renewal collection is 100. With no actual funding, it is 1,200. It is never 1,300 from counting another installment. A promise does not count as bank cash.
- Provisional agreed 50:50 can become 40:40:20 by documented effective-dated amendment and consent; this creates no formal units. At 10,000 formal units, coordinated 1,000-unit transfers by each founder produce 4,000 / 4,000 / 2,000. An independent 2,500-unit issuance instead produces 12,500 units and 40:40:20 dilution.
- Linked shareholders authorize as themselves. A non-account holder's authorization requires party-specific evidence and an expressly attributed authorized operator attestation. Governance votes never substitute for that consent, and a requester cannot approve their own ownership proposal.

Representative posted entries asserted by the PostgreSQL tests (BDT, no tax in these examples):

| Verified event | Debit | Credit |
|---|---|---|
| Actual payment for 2,500 issued units at 120 with par 100 | Bank 300,000 | Share capital 250,000; share premium 50,000 |
| Principal loan receipt | Bank 20,000 | Founder loan 20,000 |
| Founder-paid operating cost | Expense 20,000 | Founder payable 20,000 |
| Partial company reimbursement | Founder payable 5,000 | Bank 5,000 |
| Founder pays part of an existing vendor bill | AP 5,000 | Founder payable 5,000 |

The personal 10,000 transfer has no company entry. A USD 20 forecast at 100 is 2,000 base; actual posting at 120 is 2,400 base. Contribution Progress compares those retained values and discloses 400 variance rather than rewriting the saved estimate or posted journal.

## Verification evidence

| Check | Actual result |
|---|---|
| Full PostgreSQL regression | **352 passed** in 200.51s, with no warnings; includes Phases 1–4 |
| Frontend unit regression | **129 passed** in the final complete rerun after the login fix; 11 test files |
| Focused isolated Phase 5 Playwright | **8 passed**, including consumed-cycle reserve rollover/release |
| Full isolated Playwright regression | **50 passed** in **6.4 minutes**, no failures/skips; final retained database `mateerp_e2e_97ea9a5d335342a5bf763170678c996b` |
| Django/migrations/Ruff | System check passed; drift clean; all migrations applied; Ruff lint and formatting of all **268 Python files** passed |
| OpenAPI | Validation passed with fail-on-warning enabled |
| Frontend lint / TypeScript / production build | Passed again after the final login fix; normal frontend rebuilt explicitly for backend **8100** |
| Normal local smoke check | Proxy health **200**, version **0.5.0**, development database healthy, request ID present; Login **200**, signed-out Dashboard **307 → /login** |
| `scripts/verify.ps1` | All backend/frontend stages passed. Failed browser attempts were investigated and corrected; its browser stage was then rerun separately through `scripts/e2e.ps1`: **50 passed** |
| Git whitespace | `git diff --check` passed |
| Remote GitHub CI | Not run; no commit/push has occurred |

The final full run supersedes earlier checkpoint counts. Browser tests use fresh retained `mateerp_e2e_<uuid>` databases and backend 8101. Financial fixtures never target the development database.

Browser regression identified a new visual test leaving the shared account's saved theme dark; its cleanup now restores and verifies the light baseline. A later run exposed an intermittent existing login navigation race after successful authentication. Removing the immediate refresh after route replacement avoids competing navigation requests; the successful cookie/session boundary and safe redirect validation are retained. All 50 tests passed on the corrected build, including initial administrator setup, forced password changes, sessions, CSRF, billing, immutable PDFs, accounting and the new workflows. Earlier failed attempts and fixes remain documented in the progress log; skipped tests were never counted as passes.

### Acceptance coverage map

| Prompt scenarios | Principal automated evidence |
|---|---|
| A, AC — participant identity, access and private files | `founders/tests/test_api.py`; unit participant/scoped-inbox tests; Phase 5 browser setup and evidence flows |
| B, V, W, X, Y — provisional/formal events, consent, dilution, reservation and governance | `ownership/tests/test_register.py`, `test_capital.py`, `test_concurrency.py`; provisional/formal browser workflows |
| C–I, S, Z — corporate funding, loans, costs, AP, payouts and reconciliation | `founders/tests/test_corporate.py`, `test_integrity.py`, `test_fx.py`, `test_concurrency.py`; independent browser funding verification |
| J–N, AA, AB — personal sharing/history, recovery limits and policy changes | Corporate/integrity/planning tests, `test_forecast_acceptance.py`; browser confirmations and blocked reimbursement |
| O–R, T, U — monthly/annual/effective targets, reserves and FX estimates | `test_planning.py`, `test_forecast_acceptance.py`; browser forecast persistence and consumed-cycle rollover/release |
| AD — Phases 1–4 regression | Entire PostgreSQL/Vitest/Playwright suites through the existing verification runner |
| AE — approved visual identity | Browser geometry/theme/route assertions, light/dark/compact/mobile captures and visual inspection |

The evidence map identifies coverage locations; execution results are reported separately above, including any pending/failing checks.

## Design verification

Read-only prototype structures and design values were reviewed. Browser checks cover all eight founder sections and six ownership sections, valid/invalid routes, light/dark themes, 264px expanded / 64px compact sidebar, 56px header and a 390px mobile viewport. Screenshots were captured and inspected for the existing IBM Plex/Astro branding, cyan accent, sharp corners, dense tables and established spacing. Test snapshots wait for real data before final capture. This is source/value and visual review, not a claim of automated pixel-diff certification for every form.

## Data, Git and Docker safety

Final development preservation check after migrations and all browser runs: **59 users, one company, zero journals, invoices and expenses, 15 stored files** — matching the pre-migration baseline. No financial parties, founder transactions or ownership proposals were seeded. Mandatory ownership-governance settings were enabled with an append-only system migration audit record.

`mateerp-backend` and healthy `mateerp-db` remain on their loopback ports; the existing `mateerp-storage` and `mateerp-pgdata` mounts are retained. The normal API reports development version **0.5.0**, database healthy. The isolated E2E backend is stopped; its databases/files are retained. No unrelated Docker project, prototype source, production server, Git history or remote branch was modified. HEAD remains `eb9abb22ec67e7224453f5d202eecfccc933bf54` on `main`.

## Operating notes and scope limits

- Start the established environment with `docker compose up -d backend`, apply migrations, then run `npm run dev` from `frontend`. See `docs/development.md` for permission/control-account setup and Windows instructions.
- A verified local production-preview frontend is currently running on loopback port 3100, using backend 8100. Stop that preview before starting another frontend or running isolated browser tests; it does not deploy the application.
- Configure real participants, control accounts, policies and evidence explicitly. No sample founders, default 50:50 agreement or known credentials are installed.
- Reclassification/reassignment retains one original obligation per source. Use separate sources for different origins; reimbursements/repayments can allocate multiple obligations safely.
- Selection drawers load bounded reference lists (100 records); statements and directories use backend pagination. CSV exports require permission and a date range small enough for at most 10,000 rows.
- Forecasts are estimates, not postings, expense generation, guaranteed bank availability or an exchange-rate engine. No automatic loan interest accrual, tax filing, government registration or cryptographic signature certification is provided.
- Phase 4 invoice/receipt/credit-note PDF generation and historical files are preserved. Phase 5 evidence is private; no malware scanning is claimed.
- Formal share-rights/legal evidence remains the company's responsibility. The ERP records documented administrative events and their approvals.
- Phase 6 operations/reporting and Phase 7 release hardening require their own scope/review. Nothing was deployed.

## Phase 6 integration readiness

Procurement can extend the existing vendor/AP source adapters; it must not create another ledger or duplicate founder-funded settlement costs. Budgeting and cost-center work can consume immutable forecast revisions and introduce explicit source dimensions through the accounting contract. Analytics can combine posted GL reports with clearly separated forecast/contribution measures, retaining source identities and historical FX. Ownership/party and evidence references are stable for later reporting, while personal transfers remain outside corporate totals. No Phase 6 transaction workflow is implemented here.

Phase 5 is ready for owner review. There are no remaining known failing checks; Phase 6 remains subject to separate approval.

Suggested commit message after owner review: `feat: implement Phase 5 founder finance, funding plans and ownership governance`
