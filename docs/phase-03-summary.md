# Phase 3 — Core Accounting Engine delivery report

Date: 2026-10-20. Branch: `main`. Application version: `0.3.0`. Phase 4 has not started.

## A. Features completed

- Account hierarchy, active/postable accounts, protected control purposes and explicit starter-chart setup. No financial data is seeded by migrations.
- Fiscal years with twelve generated monthly periods, closing, controlled reopening, financial-history settings locks and guided opening journals.
- Draft revisions, exact validation, central posting, source identities, retry keys, journal numbering, immutable posted entries, exact reversals and linked adjustments.
- Snapshot-based financial-adjustment approvals, thresholds, separate-person decisions and revalidation of periods, carrying values and requester access.
- Cash/bank metadata linked to GL accounts; deposits, withdrawals, fees, interest, adjustments and same/cross-currency transfers through the same posting engine.
- Effective-dated exchange rates, conversion preview, immutable rate snapshots, weighted-average foreign-bank disposal and explicitly reviewed realized FX differences.
- Tax-code/mapping revisions, manual tax journal references and ledger-derived tax position.
- Manual bank statements, exact and grouped matching, conservative auto-match, unmatch, completion/reopening evidence, initial opening baselines and protection against backdated changes to completed history.
- General ledger, trial balance, P&L, balance sheet, cash movement, hierarchy subtotals, account/journal drill-down, date/period filters and authorized CSV exports.

## B. Backend changes

New domain apps:

| Files | Responsibility |
|---|---|
| `backend/apps/accounting/models.py` | Accounts, years/periods, rates, tax revisions, journals/lines, posting identities and sequences |
| `accounting/money.py`, `services/setup.py`, `services/posting.py` | Exact money, explicit setup, financial rules, posting/approval/reversal services |
| `accounting/reports.py`, `api/` | Posted-ledger selectors, SQL running balances, versioned APIs and exports |
| `accounting/migrations/0001`–`0003` | Additive schema and PostgreSQL balance, history, period, hierarchy and immutability guards |
| `backend/apps/banking/models.py`, `services.py`, `api/` | Bank metadata, treasury adapters, statement/reconciliation services and endpoints |
| `banking/migrations/0001`–`0004` | Additive banking schema, match integrity, statement baselines, evidence retention and completed-history guards |
| Both apps' `tests/` | Financial, API, direct database, report and separate-connection concurrency tests |

Existing accounts, approvals, company and core infrastructure are extended. Two sensitive permission codes are added through an additive migration. Approval uniqueness becomes `(action, subject_key)`, preserving branding's singleton behavior. `financial_history_exists()` now uses posted journals. Financial database/validation failures retain the standard error envelope and request ID.

All migrations apply successfully, including on a fresh isolated browser database. Development migrations are applied; `migrate --check` and `makemigrations --check --dry-run` pass. CI continues discovering the new pytest/Vitest tests through its existing jobs.

## C. Frontend changes

The ten existing Banking & Accounting destinations now work through real APIs: overview, bank/cash accounts, transactions, reconciliation, chart, general ledger, journals, periods, tax and statements. Detail routing lives in `frontend/src/app/(shell)/banking/[[...path]]/page.tsx`.

New components are in `frontend/src/features/accounting/`: `AccountingApp`, `Accounts`, `Banking`, `Journals`, `Reconciliation`, `Reports`, `PeriodsTaxFx`, shared typed queries/forms and exact money helpers. They provide account/fiscal/opening setup, journal lines, immutable detail/history, treasury preview/confirmation, grouped reconciliation, reports, rate history/conversion and tax mappings. Currency presentation follows company settings; authoritative amounts remain decimal strings and BigInt values.

Settings → Currency includes rate management; approval requests link to journal lines. Existing auth, company/branding, preferences, shell and planned module routes remain intact. Reusable drawer/error/dirty-state behavior, sharp corners, table styles and design tokens are retained.

## D. Accounting integrity

- Posted entries have at least two meaningful lines and exactly equal base debits/credits. PostgreSQL deferred triggers validate committed state independently of the service.
- Posted headers/lines, posting identities and FX/tax revisions cannot be rewritten. Reversals preserve original amounts/rates; corrections keep explicit links.
- Unique keys, source/action identities, reversal targets and journal numbers prevent duplicate financial effects. Identical retries return the original result; conflicting input is rejected. Even keys first seen on a replay become bound to that content.
- Financial writes serialize on the company row, then acquire domain locks in a consistent order. Posting, numbering, approvals and audit evidence commit together. Separate PostgreSQL connections test competing operations.
- Money uses `NUMERIC(24,6)` and Decimal; rates use `NUMERIC(30,12)`. Actual currency precision is enforced, with explicit `ROUND_HALF_UP` conversion. All 22 catalog currencies match database precision rules.
- Periods and completed reconciliations reject historical postings. Posted history locks base currency/fiscal start and account meaning, including summary ancestors.
- Reports derive only from posted lines. Running balances precede search/pagination; statement reports use a consistent financial snapshot. Displayed hierarchy subtotals never enter grand totals twice.

The implemented adapter contract, lock order and invariants are in [accounting-contract.md](accounting-contract.md).

## E. Security

Financial reads require `finance.view`; mutations require `accounting.manage`; period controls additionally require `accounting.periods.manage`. Financial decisions need `accounting.approve` and current accounting/read access, alongside designated-role and self-approval rules. Pending requests cannot be posted after the requester loses financial access or needs a forced password change.

New sensitive permissions are not automatically granted to existing non-admin/custom roles. Full bank identifiers additionally require `banking.evidence.view`; normal lists stay masked. Exports require `reports.export`. Session, CSRF, inactive-user and forced-password protections remain in force, including actual browser → Next proxy → Django tests. Financial setup, posting, reversal, rates, treasury, period and reconciliation actions use the existing append-only audit trail.

## F. Verification results

| Check | Result |
|---|---|
| Django system check | Pass |
| Applied migrations / migration drift | Pass / no changes |
| Ruff lint and formatting | Pass |
| PostgreSQL pytest suite | 181 passed (including 60 new financial tests) |
| ESLint / strict TypeScript | Pass |
| Vitest | 94 passed |
| Next.js production build | Pass |
| OpenAPI validation | Pass, zero warnings |
| Playwright through `localhost:3100` | 30 passed, including all Phase 1/2 regressions |
| Final report-display browser recheck | 9 passed against a fresh isolated database |
| Supported currency precision cross-check | 22 checked, no mismatches |

Backend coverage includes raw ORM/SQL mutation attempts, exact conversion/overflow, report identities, contra accounts, prior earnings/closing transfers, conflicting retries, duplicate sources/reversals, posting versus closing/settings changes, hierarchy cycles, concurrent foreign withdrawals and competing matches. Browser scenarios A–Q cover actual setup, opening/posting, rejection, reversals, locking, transfers/retries, reconciliation, historical FX, reports, independent approvals, permissions, CSRF and shell states. All Phase 1/2 regression scenarios remain included.

Browser tests now use a fresh `mateerp_e2e_<uuid>` database and optional `mateerp-backend-e2e` service on loopback 8101. Their account/company/branding/financial fixtures never reset development data. Run databases/files are retained; only the test backend is stopped. See [development.md](development.md).

## G. UI fidelity

Compared the running read-only prototype's chart, banking overview, journal directory, reconciliation, periods and trial balance in light/dark themes. Production screenshots additionally cover posted journal detail, expanded/compact sidebars and mobile navigation.

Preserved 264px/64px sidebar widths, the 56px header, Astro wordmark, IBM Plex typography, cyan accent, theme surfaces, sharp corners, page spacing and enterprise table/drawer styling. Visual review corrected account column proportions, removed extra report KPI cards, moved report filters into the table toolbar and aligned overview area-series, legends, 200px donut and recent-movements layout.

Intentional differences are real company/ledger data instead of demonstration values; hierarchy subtotals; explicit date/period controls; statement setup/completion, grouping and reopening controls; approval states; and honest Phase 6 cash-movement labeling. No pixel-difference threshold is claimed. Prototype application source was not copied or changed. Review artifacts are gitignored under `frontend/test-results/` and `frontend/playwright-report/phase3-reference/`.

## H. Known limitations and boundaries

- No invoice/payment/expense/document issuance, founder operations, inventory or Phase 4+ workflows are implemented.
- Cash movement is a real reconciled summary, not full statutory operating/investing/financing classification (Phase 6).
- No live bank connection, external FX feed, unrealized revaluation or unvalued foreign overdrafts. Foreign-bank movements must be chronological.
- Statement entry is manual. Ranges are sequential/contiguous; match groups consume whole lines. Statement CSV ingestion and partial-line allocations are deferred as approved.
- Tax position/mappings support manual journals; billing tax calculation is Phase 4, and filing is not provided.
- Closing locks dates; it does not automatically transfer earnings. Existing fiscal structures are not silently restructured when fiscal defaults change.
- The company-row mutex is a deliberate single-instance throughput tradeoff. Large exports and load/performance work remain Phase 7 concerns.
- Test databases/files are retained and consume disk; there is no automatic destructive cleanup.
- Next.js uses its supported Webpack path because this Windows environment's Turbopack CSS worker failed. No framework downgrade or validation bypass was introduced. Pinned framework/library versions are retained.

## I. Phase 4 readiness and local startup

Ready for user acceptance of Phase 3 before Phase 4 begins. Billing, payments and expenses should add source-specific adapters around `post_journal()`, preserve stable source/journal links and pending/posted states, and commit them atomically. Issued documents must reference immutable branding versions. Future modules must not introduce parallel ledgers; source-specific permissions require deliberate design.

For this existing checkout, from PowerShell at the repository root:

```powershell
docker compose up -d --build
docker compose exec backend python manage.py migrate --noinput
Set-Location frontend
npm ci
npm run dev
```

Open `http://localhost:3100` and use the existing administrator. A fresh installation uses the documented interactive `create_admin` command; there are no default credentials. Accounting setup is explicit: company defaults → chart → fiscal year → bank/cash links → reviewed opening journal.

Full checks: `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`. Browser checks require port 3100 free. See development instructions before using `npm run start` after a future E2E build, because test builds point to the isolated 8101 backend. The final delivery build has been rebuilt for the normal 8100 backend.

## J. Git and data status

Work remains uncommitted on `main`, with HEAD unchanged at `2e55e0a7933705f551ab98edf33989f15793f3f3` and remote `https://github.com/rizwansammo/MateERP.git`. No commit, push, branch, PR, merge or deployment was performed. The pre-existing untracked `AGENTS.md` was preserved.

Development inspection after migrations: 59 existing users, one company, zero accounting accounts, zero journals and zero bank accounts. Financial acceptance fixtures exist only in isolated test databases. No existing development records or volumes were deleted. Only the `mateerp` Docker project was operated. The prototype working tree remains clean.

Suggested commit message:

```text
feat(accounting): implement Phase 3 accounting engine and banking
```
