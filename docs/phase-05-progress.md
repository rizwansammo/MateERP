# Phase 5 implementation progress

## Start — 2026-10-21

- Owner approved the complete plan, four defaults and mandatory provisional-amendment, shareholder-consent and reimbursement-blocking clarifications.
- Confirmed `main`, clean working tree and expected Phase 4 base. Development data/services have not been changed.
- Created the final plan in `docs/phase-05-plan.md`.
- Current stage: foundations and governance. Next: additive models, scoped permissions, private evidence and approval quorum; then corporate finance.
- Tests: none run for Phase 5 yet. Earlier phase results are not new verification evidence.

## Foundation / corporate / sharing checkpoint

- Added financial-party identity, founder corporate source/obligation/allocation records, personal sharing/confirmation records, forecasts/reserves and ownership proposals/consents/evidence.
- Added scoped permissions, distinct approval votes and frozen ownership quorum, protected founder account purposes, private evidence policies and source-owned posting adapters.
- Implemented corporate receipt/loan/expense/AP-settlement/reimbursement services; personal sharing and confirmations with duplicate-recovery blocking; provisional amendments and formal event/consent/approval services; recurrence-based forecasting and reserve designations.
- Additive migrations applied successfully to the existing development database. No founders, shares or transactions seeded. Pre-migration preservation baseline: 59 users, one company, zero journals/invoices/expenses, 15 stored files.
- Django system check passed before API wiring. Initial focused founder PostgreSQL tests are running; no result claimed yet. API wiring/front-end integration and broad validation remain in progress.
- Important paths: `apps/{founders,ownership}`, `company.models.FinancialParty`, approval vote services, accounting control migration and purchasing founder payment mode.
- Next: resolve initial test failures, complete frontend and full acceptance coverage. Implementation is not complete.

## Integration checkpoint

- Focused founder + existing approval suite: **10 passed**. Focused ownership suite: **4 passed** (provisional amendment, atomic two-party transfer, impersonation denial and distinct/frozen quorum).
- Added real founder/ownership routes, profiles, corporate recording/preview/verification, policy/sharing/planning screens, personal confirmations, private evidence and ownership consent/review/confirmation. Strict TypeScript passed after initial integration corrections. Navigation is now Phase 5; Phase 6 remains planned.
- New API + ownership focused run: **15 passed**, including ordinary-accountant denial, private-file bytes/metadata, identity-link protection and actual multipart upload. Fixed the upload parser identified by this test.
- OpenAPI component names were disambiguated; its last schema step emitted no warnings. A subsequent migration drift step identified nullable-field metadata changes; generated those additive migrations. Full final schema/drift verification is still required.
- Extending partial company-cash coverage, funded reserve revision/rollover and exact partial consumption/release. These changes are not yet verified. Additional financial/concurrency/security tests, frontend tests, Playwright, visual comparison, lint fixes and full regressions remain.
- Preserve pre-migration baseline and volumes. No real financial fixtures, commits, pushes or deployments. Existing E2E service was already running at inspection; use only the guarded per-run runner for browser fixtures.

## Funding / governance verification checkpoint

- Implemented explicit partial company-cash coverage, exact partial reserve consumption and append-only releases, audited reserve rollover and per-founder contribution progress. Promises remain separate from posted receipts. Vendor statements now include founder-funded AP settlements without disclosing personal identity.
- Added database guards against posted-state resets, altered approval identities, altered ownership previews/consents, insufficient governance quorum and changed historical share-class rights. New additive migrations applied; Django check passed.
- First full PostgreSQL run: **329 passed, 1 failed**. The failure exposed an optional-join row-lock issue in the new reserve consumption service; corrected to lock the source row. Subsequent focused founder/ownership/approval run: **34 passed**, with a test-thread connection-cleanup warning; corrected thread cleanup and will rerun.
- Existing frontend regression: **118 passed**. Added seven Phase 5 UI tests; initial run had five passing and two test synchronization/assertion failures, now corrected pending rerun. ESLint passed before those additions; strict TypeScript passed initial planning integration.
- Added actual 2,500-unit issuance / 12,500 total dilution, capital-versus-unpaid commitments, configured par/premium and separate-connection posting/reimbursement race tests. Approval rejection/withdrawal now updates the owning founder/ownership record atomically.
- Remaining: broader FX/period/personal-resolution and security coverage, new UI test rerun, Phase 5 isolated browser scenarios, visual comparison, final full verification and documentation. Phase 5 is not complete. No development financial fixtures or Git commits/pushes.

## Browser / integrity completion checkpoint

- Phase 5 isolated Playwright run: **7 passed** (including setup). Verified actual browser/proxy/session/CSRF behavior, independent funding verification, personal confirmations and blocked recovery, external-party evidence and provisional amendments, recurrence-based planner persistence, formal 2,500-unit issuance/dilution with no invented cash, all Phase 5 routes and light/dark/264/64/56px/mobile shell checks.
- Corrected the real paginated-bank API integration error found by browser testing. Frontend tests now use the actual response shape. Full frontend unit regression: **125 passed**, ESLint and strict TypeScript passed at this checkpoint.
- Added original `recovery_origin` links and grouped payout checks across split/reclassified liabilities, immutable source-expense protection, actual corporate journal statements/CSV, historical ownership/capital dates, current company-funding coverage and exact consumption/release safeguards. Focused integrity/planning run: **12 passed**, including both repayment orders after splitting an obligation, confirmed returns and audited reassignment, AP/vendor statements, period locks and annual reserve examples.
- Additive migrations through `founders.0010` / `ownership.0006` applied; drift check clean. Ruff lint passed and all 266 Python files passed format check. No development financial records were seeded.
- Complete `scripts/verify.ps1` is now running against **346 collected PostgreSQL tests**, followed by frontend checks/build and the full isolated Phase 1–5 browser suite. Final result is pending. Agent conventions, architecture/accounting/development documentation are being reconciled; final summary/data-preservation evidence remain to close.

## Final-run checkpoint / remaining reserve correction

- Full backend verification: **346 passed**, no warnings; Django, migration drift, Ruff and OpenAPI all passed. Frontend full run: **125 passed**, ESLint/typecheck/build passed. The full **49-test** browser regression is running in `mateerp_e2e_90c0af5382be4697a1d3ca49327853fd` (`scripts/verify.ps1`, terminal session 8946).
- Development preservation rechecked: 59 users, one company, zero journals/invoices/expenses, 15 files; zero financial parties/founder transactions/ownership proposals. `main` and HEAD `eb9abb22ec67e7224453f5d202eecfccc933bf54` unchanged; existing named volumes present.
- Final review found that partially consumed reserve cycles currently block surplus rollover. Correct this with immutable retained-funding releases plus a new designation/transfer reference; never move the original consumed designation or erase its payment history. This is not complete yet and needs new PostgreSQL/browser verification after implementation.
- Added private-settlement error feedback and consent-only inbox frontend tests after the 125-test run; current frontend recheck is terminal session 88238. Final documentation still has pending verification fields. After E2E, rebuild the normal frontend against backend 8100 and verify its health/version before closing.

## Reserve correction / final acceptance coverage

- Corrected partially consumed reserve rollover using immutable releases, new retained-funding designations and explicit transfer references. Original consumption/payment history stays on the original cycle; released receipt capacity can be reused without duplicating cash. Additive migrations through `founders.0012` applied.
- Focused integrity/planning run: **15 passed**. Focused isolated Phase 5 Playwright: **8 passed**, including actual 800 consumption / 400 surplus rollover / 150 release and no extra company journal. Retained browser database: `mateerp_e2e_013bde52a85742bb810a113f45bb5ea9`.
- The earlier combined browser run finished **43 passed, 1 failed, 5 skipped**. Failure was the new Phase 5 fixture attempting chart setup after earlier phases had already configured it; corrected to reuse the isolated installation's chart. No development data was involved.
- Frontend regression after reserve/error/inbox work: **128 passed**, with ESLint/typecheck clean. Added a final historical FX/cost comparison in contribution progress, using posted source base totals against frozen forecast estimates. Its focused frontend run: **11 passed**. New PostgreSQL acceptance coverage for USD estimate-versus-actual, independent 50:30:20 sharing/self-sustaining mode and competing share reservations is pending execution.
- Combined verification is running in terminal session **88622** (349 backend tests collected before the last three test additions). Run the final new backend acceptance tests only after that pytest process completes; record the final complete results below. No completion claim yet.

## Combined regression / sequential browser retry

- Session 88622 completed: **349 PostgreSQL tests passed** in 397.09s; **129 frontend unit tests passed**, ESLint/typecheck/build passed; Django/drift/Ruff/OpenAPI passed. The browser stage failed its startup readiness check while the fresh database was still applying migrations, during the parallel follow-up backend run. No browser assertions ran in that attempt; partial database `mateerp_e2e_f0f279f8f1414c858de5f299ae4e78ad` is retained.
- Final complete **352-test** PostgreSQL run (including FX estimate/actual, custom policy/self-sustaining and concurrent share reservations) is session **82175**. Retry the isolated full browser suite sequentially after it exits to avoid startup resource contention. Do not change financial assertions or reset development data.
- Development counts and applied migrations rechecked: 59 users, one company, zero journals/invoices/expenses, 15 files, zero participants/founder transactions/ownership proposals; `migrate --check` passed. Final comparison UI unit run: 11 passed; all 268 Python files now pass formatting and Ruff lint is clean.

## Final acceptance correction

- The 352-test run finished **351 passed, 1 failed**. The new FX test verified the correct frozen 2,000 estimate, actual 2,400 posting and 400 variance, then compared the JSON journal ID string to a Python UUID object. Corrected that boundary assertion and aligned the frontend journal ID types with the actual UUID-string API. No financial calculation or posting expectation was weakened.
- Focused new acceptance recheck: **3 passed** in 26.62s, including the remaining pause/deduplication/history assertions and concurrent transfer reservations. Strict TypeScript passed after the type correction.
- Started one final sequential `scripts/verify.ps1` run with all code changes complete. No concurrent pytest/browser startup runs this time. Record its result and final normal-backend build below; all work remains uncommitted on `main`.

## Full verification / shared browser preference correction

- Final sequential runner session 38479: **352 PostgreSQL tests passed** in 200.51s, no warnings; **129 Vitest tests passed**; Django/drift/Ruff/OpenAPI/ESLint/TypeScript/production build all passed. Browser regression: **48 passed, 2 failed**. Both failures were existing shell light-theme assumptions after the new Phase 5 screenshot test left the shared administrator's persisted theme dark.
- Corrected only the new test's teardown: restore the expanded desktop/light baseline, await the real profile-save response and assert the saved server preference. Approved color/theme assertions are unchanged. Full isolated 50-test browser rerun is session **49217**, database `mateerp_e2e_ae086f837c5f48cbb1d50c819acee7c7`.
- Visually inspected the actual loaded founder light, ownership dark and 390px sharing screenshots. Existing wordmark/type, 264/64/56px geometry, cyan, sharp borders and mobile off-canvas layout are retained. No fake financial data exists in development; displayed review records belong only to the isolated test installation.

## Login navigation regression found during final browser retry

- The next full browser run exposed an intermittent initial-administrator redirect failure in the existing Phase 2 login form. Trace inspection confirmed login HTTP 200 with a 1.5s response, followed by two canceled protected-page RSC requests; the form remained in its signing-in state.
- Removed the immediate `router.refresh()` following `router.replace()` in LoginForm. The successful session response already establishes the cookie, and the route navigation loads the protected server layout. Added a regression assertion that successful login starts navigation without the competing refresh. Session/CSRF validation, credentials, redirect sanitization and authorization are unchanged.
- Focused auth/founder unit run is session 72287. The current browser process uses its earlier production build; rerun the entire isolated browser suite with the corrected build after it exits. Backend runtime is unchanged since the fully passing 352-test run.

## Completed — final local acceptance, 2026-10-21

- All seven approved implementation stages are complete. No Phase 6 work was started. The final acceptance report is `docs/phase-05-summary.md`; earlier failures/checkpoint counts above are retained as history.
- **PostgreSQL: 352 passed**, no warnings (200.51s). Financial integrity, source/GL reconciliation, duplicate recovery, immutable history, current permissions, private files, FX, concurrent payouts/share reservations and Phase 1–4 regression are included. Django/drift/applied migrations/Ruff/OpenAPI passed; 268 Python files pass formatting.
- **Final frontend: 129 passed**, 11 Vitest files; ESLint and strict TypeScript passed after the login fix. Production builds passed for both the isolated test backend and explicitly restored normal backend 8100.
- **Full isolated Playwright: 50 passed**, no failures/skips, in 6.4 minutes (session 52229). Includes initial bootstrap, login/session/CSRF, users, permissions, administration, Phases 3–4 finance/documents and all Phase 5 browser workflows. Database/files retained in `mateerp_e2e_97ea9a5d335342a5bf763170678c996b`; test backend stopped normally. No financial assertions were weakened.
- Final normal proxy smoke: localhost:3100 health 200, development version 0.5.0, database healthy and request ID present; Login 200; signed-out Dashboard 307 to Login. Native production preview is running on loopback 3100 in terminal session **15360**, connected to backend 8100. Stop only this preview before another frontend/E2E run; do not touch unrelated processes.
- Final preservation counts: **59 users, one company, zero journals/invoices/expenses, 15 stored files, zero financial parties/founder transactions/ownership proposals**. Same pre-migration development baseline. Named volumes `mateerp-pgdata` / `mateerp-storage` remain mounted; normal API and healthy database remain running.
- `main`, HEAD `eb9abb22ec67e7224453f5d202eecfccc933bf54` unchanged. Git whitespace check passed. All changes remain uncommitted; no branch, commit, push, deploy or remote CI run occurred. No prototype/unrelated repository or Docker project modified.
- Important deliverables: `apps/founders`, `apps/ownership`, company financial parties, scoped accounting controls/adapters, immutable approval votes, private evidence policies, `features/founders`, `features/ownership`, real routes and the documented integration/acceptance contracts. Known scope limits and Phase 6 integration points are in the summary.
- Next action: owner review and owner-managed commit. Suggested message: `feat: implement Phase 5 founder finance, funding plans and ownership governance`.
