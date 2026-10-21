# Phase 6 implementation checkpoint

## Current state

**2026-10-22: Phase 6 complete for owner review.** Milestones 6A–6D are implemented.
Full backend campaign:409 passed; final readonly inventory target5 and company
settings target18 passed. Full frontend:154 passed. Final isolated browser run:
**60 passed (14.3m)**, including all Phase1–5 regressions, in retained database
`mateerp_e2e_225f606546b74e3896630548c778c4af`.
Final lint, strict TypeScript/production build, schema and migration checks passed.
Five final visual captures were reviewed against the read-only reference.
See `phase-06-summary.md` for scope, accounting examples, limitations and results.

Normal8100 production build and native3100 preview are restored (session4059).
Same-origin health200 reports0.6.0/databaseOK, Login200, protected pages307 toLogin.
The E2E backend and temporary reference3102 preview are stopped; normal API/DB run.
All work remains unstaged/uncommitted onmain at the original HEAD below.
No Phase7 work is authorized. **Next action: owner reviews and commits; do not
continue ordinary development or begin Phase7 without a new owner instruction.**
Earlier sections below are chronological development history, not outstanding work.

Owner approved Milestones 6A–6D with mandatory historical onboarding,
pre-registration expenditure and explicit control-transfer clarifications.
The final approved plan is in `phase-06-plan.md`.

Baseline: clean `main` at `aec67d23203f14eaa25642a4dd405be1d876bdb8`.
No commits, branches, pushes or deployment. Development data/volumes untouched.

## Verification actually performed

Read-only preflight: correct main/remote; MateERP containers and retained volumes
present; direct and same-origin health HTTP 200; Django check clean; migrations
current; migration drift check clean. Phase 5 results are historical evidence,
not Phase 6 passes (352 backend / 129 unit / 50 E2E previously).

Development baseline: 59 users, 1 company, 15 private files, zero accounts,
journals, banks, invoices, bills, expenses, billing items and founder financial
sources. Never seed financial fixtures into this installation.

## Implemented so far (not final acceptance)

- Approved plan recorded with all three mandatory clarifications.
- Source/prototype extension points inspected without changing the reference.
- Catalog profiles preserve BillingItem IDs; category/unit configuration, dated
  immutable prices, exact quotation/margin API and catalog/pricing drawers/pages.
- Purchase orders with frozen approval snapshots, issue/cancel/close, partial goods
  receipts and service acceptance; exact receipt/bill matching clears GRNI in the
  existing vendor-bill posting workflow. Orders themselves post no journal.
- Initial inventory quantity/cost events, company-wide weighted average, locations,
  transfers/count adjustments, chronology checks and reconciliation; corresponding
  production pages are written. Movement rows are append-only in PostgreSQL.
- Historical non-posting evidence registry, mandatory independent recognition
  review, original-vs-recognition expense dates, preparation of existing expense /
  founder drafts, and reviewed opening bank/vendor/founder sources. Opening and
  reconstruction are mutually exclusive per provenance record. Initial inventory
  opening integration is written but not yet tested.
- Additive operational control purposes and permissions; existing roles/data remain
  unchanged. New code has not yet been marked delivered in global navigation.

Actual tests: initial catalog suite 4 passed; catalog + initial procurement/stock
suite 8 passed; affected accounting + historical onboarding + catalog/stock suite
**64 passed (48.10s)**. Frontend TypeScript passed after catalog/procurement pages.
Inventory UI and subsequent changes still need checks. New files have been
formatted once; remaining lint diagnostics need repair. No E2E or full final run.

Additional checkpoint: private procurement evidence, amendment drafts and retained
independent PO approval quorum implemented; historical rejected reviews may be
resubmitted without deleting earlier evidence. Targeted 9 backend approval/evidence
and historical tests passed after fixing streaming-test transaction handling.
OpenAPI validation now has **zero warnings/errors**. New UI unit suite: **6 passed**.
ESLint passed; production build passed. Targeted E2E first reached the real stock
valuation but expected currency-code presentation while company defaults used the
correct BDT symbol. Assertion now targets exact value in the SKU row and separately
checks API currency/value/reconciliation. Rerun pending. This is not final acceptance.

The old native preview (tool session 15360) was explicitly stopped to free 3100.
The current `.next` build proxies to isolated backend8101; rebuild with backend8100
before restoring a normal development preview. E2E scripts stop only the isolated
backend after each run and retain each fresh database. Development migrations have
not yet been applied; no financial fixtures entered there.

## Checkpoint — resumed 2026-10-21

Working tree remains uncommitted on `main`. No reset, stash, commit, push or volume
removal. Additive development migrations through purchasing0008/accounting0010
have been applied. Read-only counts remained User59, CompanyProfile1, StoredFile15,
and no accounts/journals/invoices/expenses/vendor bills. No financial fixtures were
entered into development.

Additional actual verification: broad affected PostgreSQL financial regression
suite **194 passed (166.45s)** before fulfillment hooks; targeted isolated browser
suite **4 passed (1.3min, including authentication setup)**. Retained test database
`mateerp_e2e_4afacc5b5b094e7c8dd67b35d4683ce5`. New fulfillment tests **4 passed
(29.23s)** after resume, covering dispatch, cross-period control/invoicing,
pre-delivery credits and original-cost customer returns. These are targeted
results, not final Phase 6 acceptance.

Fulfillment source models, frozen invoice allocations, control-based recognition,
customer returns and dispatch recalls are written. Additive billing0004–0006 and
inventory0004 migrations exist but have not been applied to development. API
wiring is newly added and still needs integration checks; UI is next. The old
native preview has been stopped. Current `.next` points to isolated backend8101;
rebuild for backend8100 before restoring a normal preview.

## Additional checkpoint — fulfillment and initial assets

- Fulfillment API and production order detail are connected. Source-owned recalls
  are retained and guarded in PostgreSQL. New frontend tests cover separate
  dispatch/control presentation and exact decimal/evidence submission (run pending).
- Physical count requests now freeze quantity and valuation provenance, enforce
  configured independent approvals, reject stale review, and retain outcomes.
- Supplier acquisition price corrections retain original receipts and journals,
  split the explicit delta between retained stock and consumed cost, freeze review
  basis, and feed corrected exact bill matching. New GRNI source reconciliation and
  deferred database guards are written. Corrections of already-posted matched bill
  consideration are blocked rather than silently editing historical purchases.
- Historical reconstruction uses the documented gross amount including tax,
  preserves journal vs recognition dates, freezes adopted draft identity and
  blocks ordinary founder recording against reserved historical references.
- Fixed-asset backend and UI are written: source claims, capitalization,
  straight-line schedules/actual charges, prospective estimates, sale/retirement,
  partial disposal-month depreciation, private evidence and reconciliation.
  Initial tests: **6 passed (30.07s)** after repairing a SQL variable ambiguity.
  Acquisition/source reversal and retained disposal-invoice changes are blocked.

Actual additional checks: count + historical target **9 passed (40.46s)**; supplier
cost correction target **2 passed (40.78s)**. Earlier inventory/history target was
20 passed/1 failed (double save after count posting), corrected and targeted rerun
passed. Frontend TypeScript passed after fulfillment/cost correction; six existing
operations unit tests passed before new fulfillment tests. Asset UI and expanded
unit suite still need checking. No new development migrations applied since the
prior checkpoint; billing0004–0007, inventory0004–0006, purchasing0009–0010 and
assets/files additions remain additive pending development application.

Next: verify assets + shared financial regressions, finish historical/source and
operational edge cases; implement cost centers/budgets and reporting/dashboard;
then isolated browser acceptance and the comprehensive final campaign. Global
navigation still marks Phase 6 planned until integrated features are validated.
This is not a completion report. No commit/push/deploy or Phase 7 work.

## Additional checkpoint — initial budgets and wider regression

Affected Phase 1–6 financial regression suite **210 passed (159.94s)** after the
fulfillment/count/cost/asset integrations, before budgeting was introduced.
Budget target **4 passed (30.26s)** after fixing an explicit query output type.
Operations frontend unit suite **8 passed**, now including fulfillment evidence
submission. TypeScript passed after asset UI (before latest budget UI). Current
lint/schema/type runs are pending; formatting/import sorting has been scoped to
new Phase 6 modules. Remaining lint items are known and must be fixed.

Written budgeting functionality: cost centers, append-only analytical assignments,
source attribution inherited by asset reclassifications/depreciation, monthly/
annual exact budgets, retained independently approved revisions, active-scope
overlap protection, original/revised/posted actual comparison and journal drilldown.
Production pages exist at `/budgets/*`; source classification is also linked from
posted bills/expenses. New budget migrations have not been applied to development.

Next: repair remaining lint/schema/UI issues and add isolated fulfillment/asset/
budget browser scenarios. Complete historical integration and 6D reporting/
dashboard, then final acceptance/regressions. No Phase 6 completion claim yet.

## Remaining

- Finish 6A–6C integration/edge cases (dated prices in commercial forms, source
  attribution in official project profitability, privacy/concurrency/rounding and
  operational summaries). Current source code is reusable; do not restart it.
- Complete and verify 6D dashboard/report library/projections, classified cash flow,
  filters and bounded exports. Reporting selectors/API/UI are newly written and
  need broader integration coverage.
- Complete browser acceptance, visual comparison, navigation/version updates,
  architecture/accounting/development docs and the final full verification campaign.

## Resume from here — exact next actions

Latest checkpoint: source search now includes retained supplier/expense/founder
references (asset target **6 passed, 32.88s**). Historical source linking handles
verified corporate funding/reimbursements and confirmed personal settlements,
without reposting; private personal provenance is scoped. Historical/core-report
target **10 passed, 33.96s**. Initial reporting target **4 passed, 50.69s**, covering
cash-flow classification/reconciliation, as-of GL aging, dashboard permissions and
bounded/formula-safe CSV. Additional operations UI target **11 passed**.

Expanded E2E currently has **5 passing, 1 failing, 1 not run**: fixture controls were
fixed; the latest failure identified asset-source search by original line description
which posted journal summaries do not preserve. Supplier-reference search has been
implemented and backend-tested; rerun the browser suite using a new build. Failed
runs retained `mateerp_e2e_796baf4ea560435086d7fc34c21e82f8` and
`mateerp_e2e_9cf1ef904fd1450e93e86e5f0fd4cd13`. No dev financial fixtures were used.

Current reporting code: `apps/reporting/` and frontend
`features/operations/{Dashboard,CashFlow,Reports}.tsx`. New API/schema and full UI
checks are pending after those latest files. Latest OpenAPI validation before the
generic DataView was warning/error-free. Several formatting/lint fixes remain in
new and touched Python files; do not suppress lint rules.

Poll current type/lint tool sessions if still running, then fix failures and add
report projection tests (recurrence uses the existing template/interval contract).
Finish report routes and meaningful filters, attribution and source integrity.
Run the expanded isolated browser test with a fresh build; no frontend preview is
currently running. `.next` is configured for test backend8101. Rebuild for backend8100
before restoring a normal preview. Development migrations after accounting0010 /
purchasing0008 have not yet been applied; all later migrations are additive and
tested through PostgreSQL pytest. Apply them safely, check original dev counts,
then finish acceptance. No commits, pushes, deployment, resets or Phase 7 work.


## Resume checkpoint — reporting integration and preserved development records

- All additive migrations through accounting0011, billing0007, inventory0006,
  purchasing0010, assets0002, budgeting0002 and reporting0002 are applied.
  Development counts remain User59, CompanyProfile1, StoredFile15, Account0,
  JournalEntry0, Invoice0, Expense0 and VendorBill0. No financial fixtures ran there.
- Project profitability now includes source-owned control-transfer revenue,
  returns, capitalization reclassification and actual depreciation. Targeted
  billing/project + fulfillment + asset checks: **16 passed (44.75s)**.
- Initial reporting and asset checks after native acquisition-cost allocation:
  **12 passed, 1 failed (43.33s)**. The failure was a too-short test posting key,
  corrected to the valid existing 8–160-character contract; rerun pending.
  Recurring net run-rate/draft exclusion passed. Backend Ruff now passes globally.
- Frontend strict TypeScript passes. Operations unit suite **15 passed (6.30s)**,
  including dated server price application/tax-mode rejection, report authorization,
  real filter/sort/export parameters and restricted dashboard state.
- Reporting UI/API now includes source filters, exact numeric sorting before string
  serialization, source drilldown and safe bounded exports. Catalog quotations
  need finance.view, not catalog-edit authority. Explicit dated-price application
  is connected to orders, invoices, recurring schedules and purchase orders;
  historical/edited prices are never silently overwritten.
- Expanded isolated browser campaign is running in retained database
  `mateerp_e2e_c372698e8c5040d5a04b201c548dd32a`, including the asset reference-search
  fix, budget approval and reporting/dashboard. Its results are not yet known.

Next: inspect that campaign, finish remaining supplier-return/correction and
operational edge cases, add financial/privacy/concurrency coverage, then navigation,
visual acceptance and final comprehensive verification/documentation. No completion
claim, commits, pushes, deployments or Phase 7 work.


## Current checkpoint — full campaign underway; preserve this state

Latest owner progress response: approximately **75% overall**, then continued.

- Expanded isolated browser suite: **8 passed (1.6m)** in retained database
  `mateerp_e2e_c372698e8c5040d5a04b201c548dd32a`. Includes actual receiving/evidence,
  historical evidence with no GL, control transfer, capitalization/depreciation,
  independent budget approval and dashboard/report CSV filters.
- Added unmatched supplier returns and exact remaining receipt matching/GRNI
  reconciliation, plus linked cost-only stock corrections. Target **7 passed
  (35.54s)**. Independent-connection stock/acquisition/depreciation concurrency
  checks **4 passed (35.54s)**.
- Added unused-capitalization reversal/replacement, historical/source attribution,
  budget CAPEX cancellation handling and efficient cash-flow classification.
  Assets + budgeting + reporting **21 passed (45.77s)**, BEFORE the subsequently
  identified historical claim-release chronology safeguard/test. Assets0005 adds
  that safeguard; it still needs targeted verification/application to development.
- All additive development migrations through assets0004, inventory0007 and
  purchasing0012 applied. Original development records/volumes retained. Only new
  historical privacy tests use stored test images. Prototype git status is clean.
- Navigation now CURRENT_PHASE6; version0.6.0 markers updated. The expanded browser
  file now also tests supplier return/cost correction, capitalization reversal and
  all shell states, with optional local prototype capture.
- Latest full frontend run: **143 passed, 1 failed**, because a chart empty-state
  test still expected fiscal-year wording after selectable periods were added.
  Updated to the truthful selected-period wording. Added correction UUID/margin
  scenario coverage afterward; rerun pending. Strict TS and ESLint passed before
  those latest additions.
- Comprehensive `scripts/verify.ps1` currently running, log retained at
  `backend/.cache/phase-06-verification.log`. It collected **409 backend tests**;
  one seen failure was the obsolete expectation that PO approval remained planned.
  The owning Phase 6 approval is implemented/tested; expectation updated to True.
  Complete results are not yet known. Do not claim this campaign passed.
- Local read-only prototype preview is running on127.0.0.1:3102 (tool session71505),
  using its existing build, with telemetry disabled. Production `.next` last built
  for test backend8101; normal preview remains stopped. Stop the reference server
  after visual review. No prototype modifications, commits, pushes or deployments.

Exact next steps: inspect the full verification log and fix actual failures. Recheck
assets0005/source-release chronology and apply its additive migration; add any
remaining meaningful report/source/UI tests. Finish visual comparison from local
E2E screenshots; update the acceptance summary and documentation with actual results.
Run affected checks after fixes (the final comprehensive baseline includes the
whole Phase 1–5 suite), restore an8100 frontend build and confirm final scoped Git/
Docker/counts state. Do not start Phase7. Keep all changes uncommitted on main.

## Resume checkpoint — comprehensive financial regression passed

Owner progress update: approximately **85% overall**; implementation continues.

- Corrected campaign `backend/.cache/phase-06-verification-final.log`: **409 backend
  tests passed (419.16s)**, including Phase 1–5 regressions and independent-connection
  concurrency. The earlier 408/1 result was an obsolete PO approval expectation;
  actual frozen PO approval is now implemented. Targeted source-chronology/approval
  checks also passed **13 tests (56.00s)**. Assets0005 applied additively.
- Frontend full run before this campaign: **146 passed (57.56s)**. Removed an invalid
  Testing Library option and bounded Vitest to two workers to avoid unrelated
  Windows resource contention; no assertions or timeouts were weakened.
- First campaign's isolated backend timed out while migrating a fresh database.
  The runner now has a bounded configurable 600-second startup allowance and
  fails promptly on a genuinely stopped backend. Its incomplete test DB is retained.
- Second complete verification campaign still running (tool session2827); remaining
  schema/frontend/build/full isolated E2E results must be inspected before acceptance.
- Read-only prototype preview on127.0.0.1:3102 (session29214) uses an ignored launcher
  with filesystem mutation guards beneath the prototype. Initial screenshot showed
  matching shell geometry but missing inventory KPIs/chart in production. Added real
  `/inventory/summary/` and production KPI/reorder/chart components with quantities
  kept separate by unit. These last readonly changes postdate backend suite imports:
  targeted stock tests are running (session28106); new frontend coverage is included
  in the ongoing frontend campaign. Scoped Ruff passed after formatting.
- No development records, volumes or prototype sources changed. No commits, pushes,
  branches, deployment or Phase 7. Stop created reference preview after visual review.

Next: resolve any actual verification failures, inspect light/dark/compact/mobile
screenshots, finish acceptance documentation, restore normal8100 frontend build,
then confirm scoped Git/Docker/data/prototype state and give the owner the commit
message. Keep all current tracked/untracked changes.

## Resume checkpoint — final browser failures isolated; fixes under verification

- Full campaign: PostgreSQL **409 passed**, frontend **147 passed**, lint/strict TS/
  schema/build passed. Last readonly stock-summary target **5 passed (88.31s)**.
  Later operations/chart/display target **42 passed (14.79s)** with lint/TS passed.
- Full browser run in retained DB `mateerp_e2e_dd842a6677b7418291fda968f0a5a739`:
  **45 passed, 3 failed, 12 did not run (7.5m)**. Preserve its traces/logs.
  Actual root causes: (1) new optional-module routes bypassed the existing disabled
  notice; stock writes still correctly rejected on the server; (2) an obsolete
  Phase4 test still expected purchase orders to be planned. Phase6 location creation
  then failed because the earlier failed module-toggle scenario left inventory off.
  Earlier commentary initially suspected only an obsolete assertion; the full
  error clarified the real route-guard gap. Do not misreport this as all tests passing.
- Extended existing ModuleRoute to guard working child screens, wait for settings,
  fail visibly on configuration errors and retain permission checks. Applied to
  inventory/assets/budgets/procurement and existing founder/ownership routes.
  Metadata now explicitly marks the six implemented optional modules Functional.
  Future definitions default to unimplemented; no blanket future phase activation.
  Backend company target running (session19334); full frontend checks running
  (session69604), including four added guard/status tests. No financial posting
  behavior changed by these final integration fixes.
- Added exact display-only budget utilization (10000 plan /8000 actual =80%,2000
  remaining), and compact inventory chart/trimmed quantity formatting to match the
  observed prototype summary/table proportions. Inventory reconciliation remains
  visible after the overview table. Final E2E rebuild must include these changes.
- Latest dev counts unchanged:59 users,1 company,15 private files; zero accounts,
  journals/invoices/expenses/vendor bills. Prototype Git status clean. Reference
  preview still session29214 on3102; normal preview stopped; no commits/pushes.

Next: inspect target checks, then rerun all60 isolated Playwright tests in a fresh
database (do not reuse the failed run's partly changed settings). Inspect final
light/dark/compact/mobile screenshots and reference. Finalize acceptance docs,
restore8100 build, stop only the created reference preview and confirm scoped
Git/Docker/data preservation. Do not rerun financial fixtures on development.

Follow-up: company settings **18 passed (29.77s)**; full frontend **151 passed
(22.80s)** with lint/strict TypeScript passed after the guard/status changes.
Full browser rerun is active in session22450, log
`backend/.cache/phase-06-browser-final.log`, fresh retained database
`mateerp_e2e_196c34ef1c5c4be9a15498fcb68ecec1`. The previous three failed traces were
copied to ignored `backend/.cache/phase-06-failed-browser/` before the rerun.
No remaining check may be claimed passed until the rerun output is inspected.

Second full browser campaign: **55 passed /1 failed /4 not run (6.2m)**. All
Phase1–5/browser regressions now passed. The remaining failure was fixture-only:
budget setup chose the first fiscal year, which the earlier accounting scenario
had made2027, for an October2026 line. The backend correctly rejected that invalid
allocation. Fixed the test to explicitly select the fiscal year containing its
October dates; no financial validation was changed. Budget failure trace retained
with the earlier traces. A targeted Phase6-only fresh isolated rerun is underway
(`backend/.cache/phase-06-browser-target.log`), reusing the already current8101 build.
Next inspect the remaining new supplier/correction/reversal/visual scenarios, then
run the complete60-browser suite again. Final acceptance remains pending.

The focused run then exposed a second fixture race: it read a revision before
the asynchronous submit request finished and called `/requests/null/approve/`.
The retained network trace confirmed the null ID; no authorization rule failed.
The test now waits for submission completion and asserts pending status/non-null
approval before testing the unchanged403 self-approval assertion. Focused rerun
session62433 uses fresh DB `mateerp_e2e_73cda89d1c3c4875b2319cf9a6319c7d`, log
`backend/.cache/phase-06-browser-target-final.log`. Prior6-pass/1-fail/4-not-run
target and its trace are retained separately. OpenAPI validation reran successfully
after final company metadata changes. No application source changed for either
budget fixture fix; current8101 production build remains valid.

Focused Phase6 browser verification **11 passed (1.7m)** in the73cda89d database,
including all newly added supplier return/correction/reversal and visual scenarios.
Full60-browser rerun active in session55209, fresh retained DB
`mateerp_e2e_8a73154f7c2242e9a52d7fa209798f8b`, log
`backend/.cache/phase-06-browser-acceptance.log`. It uses the prior current build.

Visual inspection of those screenshots caught a real presentation defect: an
existing shared formatter returned an unprefixed raw fractional cost on its fallback,
and symbol presentation blindly removed the expected currency-prefix length.
For650/7, the correct stored average92.857143 appeared as57143. Fixed formatting to
preserve all significant fractional digits with exact integer grouping and retain
the prefix on fallback. No inventory or ledger value changed. Added three unit/hook
regressions; full frontend check session4623 is running. Sidebar footer phase text
also updated to6. These final presentation changes need a new production build
and the focused operations browser suite after the full baseline run finishes.
Do not rebuild `.next` while its active Playwright server is using it.
Target screenshots retained in ignored `backend/.cache/phase-06-visual/` for review;
regenerate final captures after the fractional-display fix before final acceptance.

Full baseline rerun ended **56 passed /1 failed /3 not run (9.1m)**: the dashboard
test incorrectly expected only its own400 revenue, ignoring2321 created by earlier
phase scenarios. Replaced the fixed total with an independent exact posted-GL
revenue sum for the explicit custom interval; retained the separate source-specific
400/200 control/COGS checks. No report calculation was changed. Prior trace retained
under `backend/.cache/phase-06-failed-browser/dashboard-cross-phase-total/`.

Fractional-display fix: **all154 frontend tests passed (56.66s)** with lint/strict
TypeScript. Added browser assertions for92.857143 unit cost and updated phase footer.
Now running a new build plus full60-browser verification in a fresh isolated DB,
log `backend/.cache/phase-06-browser-verified.log`. It must include the final formatter
and footer changes. No parallel full-suite jobs remain. Wait for this result, inspect
new screenshots, then finalize docs and restore normal8100 preview. Keep reference
server29214 running until its final reference capture; stop it afterward.

Exact active run: session35169, retained DB
`mateerp_e2e_010936814536459a8b3429f40cf9feb6`. This build includes all154-test
formatter regressions and the phase6 footer; schema/lint/type checks are green.
All scoped additive development migrations were confirmed applied. Original
volumes `mateerp-pgdata`/`mateerp-storage` are present with the local driver.
Final normal-development read-only counts: User59,CompanyProfile1,StoredFile15;
Account/JournalEntry/Invoice/Expense/VendorBill/HistoricalRecord/ItemProfile/
Movement/Location/Asset/Budget all0. No isolated fixtures leaked into development.
Do not rebuild the active `.next` until the run finishes. Next: inspect run result,
review the corrected screenshots, stop only reference session29214, rebuild with
backend8100 and restore native3100 preview, finish acceptance docs and final Git
check. All work stays uncommitted on main; no Phase7.

## Final browser-response checkpoint — 2026-10-22

The final-build run retained DB `mateerp_e2e_010936814536459a8b3429f40cf9feb6`:
**55 passed /3 failed /2 not run (12.9m)**. All ten Phase6 business/visual tests
passed, including fractional unit-cost display and independent dashboard/GL totals.
Failures were older browser-readiness races: the capital projection was still
loading; theme reload aborted its pending account preference PATCH; sidebar expand
was likewise aborted on context teardown, leaving the next test compact. Retained
network traces show the aborted PATCH and the eventual successful capital response.
The fixtures now await the actual successful projection/preference responses and
assert saved values. No timeout, financial assertion or access control was weakened.
The Phase6 visual test also awaits each preference write before closing its page.

Fresh full60 isolated rerun: session65924, DB
`mateerp_e2e_c9c29b2fb98d46febde4fa458d2c9c98`, log
`backend/.cache/phase-06-browser-final.log`, reusing the final production build.
Reference server29214 remains read-only on3102. Native3100 preview is reserved for
Playwright. Final normal8100 build/preview and acceptance docs remain pending.

Latest full rerun: **57 passed /3 failed (10.5m)**; inspect the log for exact duration.
All financial scenarios and the previously failing capital projection passed.
The three preference/visual failures were `savedPreference is not a function`:
the shared helper changed after Playwright global setup had already imported its
old module. This was an agent sequencing mistake, not an application failure.
No further edits will be made to test modules while the next run is initialized.
Final screenshot capture now also waits for the actual fractional-cost row and
stock-value chart before capture. Fresh full acceptance rerun follows, with all
helper edits already on disk; no application rebuild is needed.

Final acceptance run (all edits completed before initialization): session18803,
retained DB `mateerp_e2e_225f606546b74e3896630548c778c4af`, log
`backend/.cache/phase-06-browser-final-acceptance.log`. Do not edit support/spec
modules or rebuild `.next` during this run. Final normal8100 preview, screenshot
review and documentation status changes follow only after the run completes.
Latest backend check/schema/lint passed; no missing migrations;346 Python files
already formatted. Latest frontend lint and strict TypeScript passed after the
shared helper was written. There are no application changes since154 unit tests
passed; the only subsequent changes are browser synchronization/assertions and docs.

## Final acceptance checkpoint — 2026-10-22

Session18803 finished successfully: **60 passed,14.3m**, exit0, retained225f6065 DB
above. All three previously failing helper/preference checks passed, with saved
values and reload behavior still asserted. No tests were skipped or assertions
weakened. Final summary row/stock chart readiness was checked before screenshots.
Reviewed all five final captures (light/dark/compact/mobile and reference); full
fractional92.857143 display is correct. Final copies are in ignored
`backend/.cache/phase-06-visual/`. Reference repository stayed clean and its preview
was stopped intentionally after capture.

Final native build session44376: ESLint and production build/type checks passed.
Its route manifest proxies both API forms to8100. Native preview session4059 is
running on3100; health/login200, anonymous dashboard/inventory307 toLogin. Public
health returns0.6.0 and databaseOK. Only MateERP API8100/DB55432 remain running;
test backend8101 is exited. Both existing volumes remain. All source/docs are
uncommitted onmain, original HEADaec67d2; no staged changes, commit, push or deploy.

No implementation tasks remain within the approved Phase6 plan. Detailed acceptance,
known operating boundaries and owner commit message are in `phase-06-summary.md`.
Stop here for owner review. Phase7 requires separate explicit approval.
