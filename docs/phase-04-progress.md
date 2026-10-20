# Phase 4 resume checkpoint

Resumed 2026-10-20 from Claude's uncommitted working tree on `main`, HEAD `ab116a0b6c3860bc813cd40625d65296b466ff39`. No reset, stash, commit, push or replacement checkout.

## Recovery inspection

- Reusable: sales, billing, purchasing and documents backend domains; migrations through `sales.0002_order_totals` applied; shared commerce components and partial customer/order/invoice/payment/credit screens.
- Partial: frontend sales integration and document previews.
- Missing: upload drawer, sales overview/receipts/recurrence/projects/router, purchases frontend/router, document explorers, navigation/setup integration and new frontend/E2E tests.
- Verified: expected branch/base/remote; only MateERP backend/database running; migration check passes. Initial TypeScript check finds three errors (missing UploadDrawer, unknown error rendered as ReactNode, inferred order-line payload type).
- Running: full inherited PostgreSQL suite (268 tests collected). Claude's earlier 266-pass result is supporting evidence only.
- No material access blocker. `docs/phase-04-plan.md` is absent; continue the already approved scope from the handover and actual source without another planning gate.

## Next action

Resolve frontend blockers; complete API-backed sales, purchases and document filing, then run full verification, visual comparisons and final documentation. Preserve all existing changes and development data. Test financial fixtures only in isolated test databases.

## Frontend implementation checkpoint

- Inherited full PostgreSQL suite: **268 passed** (213.58 seconds). Initial sales/upload additions passed strict TypeScript.
- Added missing upload drawer; corrected order totals and line payload types. Added sales overview, receipts/detail, projects/milestones/detail, recurring billing/history, posting defaults/catalog and SalesApp/catch-all route.
- Added vendors/detail, bill/expense editors and posting/detail, vendor-payment preview/confirmation/detail, recurring expenses/history, purchasing overview/history and PurchasesApp/catch-all route.
- Added private client/vendor explorers with folder tree, breadcrumbs, search, sort, list/grid, paging, metadata/archive and viewer. Improved viewer keyboard/focus, PDF zoom and fullscreen.
- Full frontend integration is still being checked. First lint identified synchronous-effect state initialization in inherited calculation/editor components; refactored to keyed asynchronous calculations and initialized editor form state.
- Relevant confirmed gap to fix: receipt/payment proof folder queries currently associate only the first allocation and use payment year rather than invoice year. Add derived multi-invoice filing queries without regenerating/duplicating official PDFs.
- Next: finish filing lookup/navigation/approval links; add missing tests, run isolated Phase 4 browser scenarios and full regressions; document exact results. No completion claim yet.

## Integration checkpoint — 2026-10-21

- Completed all sales/purchases routes, private client/vendor explorers, posting setup, navigation, permissions, approval review links and exact document display models. Existing Phase 4 backend retained.
- Fixed actual integration defects: tax IDs incorrectly coerced to numbers; an asynchronously loaded base currency displayed without being submitted; stale draft calculation results; invoice issue retry creating another draft; multi-invoice receipts filed in only one invoice/year; project margin including output tax; credit/refund/application idempotency keys accepting different payloads; amount-in-words overflow for large values.
- Added immutable credit/refund/application request fingerprints (`billing.0003_credit_request_identities`, additive migration applied). Concurrent retries now tested with separate PostgreSQL connections. Historical records are retained.
- Added posted-ledger fiscal charts, prototype aging/category/vendor panels, exact historical base project profitability and linked project cost lines. Multi-page PDF rendering now reserves a top margin on every page.
- Verification actually completed: inherited PostgreSQL suite **268 passed**; frontend TypeScript and ESLint passed; full frontend unit suite **113 passed**; focused credit identity/concurrency + project + all PDF templates **17 passed**. Earlier filing/project/formatting focused runs also passed.
- Isolated browser acceptance has passed customer/order/invoice, exact discounts/tax, payment verification and partial/multi-invoice settlement, credits/refunds, bills/vendor payments, paid/accrued expenses, recurrence, projects, private-file upload/authorization/preview/archive and disclosed FX confirmation. Period-lock test expectations are being aligned with the existing Phase 3 validation envelope (400 with an open-period error, no financial mutation).
- Current work: final focused tests for cross-currency project costs, dry-run scheduling and chart values; rebuild/rerun all Phase 4 browser scenarios; compare production screenshots with read-only prototype and inspect multi-page PDFs; then full verification/regressions and final documentation.
- Important new files: `features/{sales,purchases,filing,commerce}` frontend modules; `billing/services/overview.py`; `documents/selectors.py`; `documents/api/references.py`; new commerce unit/Phase 4 E2E tests and financial/document regression tests. No commit, push, reset, stash or development-data fixtures.

## Final verification checkpoint — 2026-10-21

- Resumed after the account usage reset. Working tree/base/remote are unchanged; only MateERP backend/database were restarted using existing volumes.
- Full PostgreSQL suite: **301 passed in 233.95 seconds**. Django checks, migration drift check, Ruff lint/format, OpenAPI with fail-on-warning, frontend lint and strict TypeScript passed.
- Focused commerce UI tests: **24 passed**, including very large/negative chart values, correct purchase-order Phase 6 status and unsaved order/payment protection. Full frontend suite/build/browser regression is in progress through `scripts/verify.ps1`; log retained at ignored `backend/.cache/phase4-verify.log`.
- The previous focused browser run passed all financial scenarios (13 tests including setup), then found the final purchase-order phase-label defect. Corrected the shared planned-page component and covered it in a unit test. Final E2E adds light/dark/compact/mobile captures and explicit 264/64px sidebar and 56px header assertions.
- Raster inspection of all document layouts and multi-page continuation/final pages completed. Safe per-page top margins prevent header overlap; 90 lines and final totals remain present in each template.
- Final report draft: `docs/phase-04-summary.md`; architecture/accounting/development/design/README and both agent instruction files updated. Replace pending final evidence only after the complete run finishes, inspect production screenshots, restore the normal 8100 production-build proxy and perform the final Git/Docker/data audit.

## Final quote and regression correction

- The first combined verification passed 301 backend tests, 118 frontend tests and all non-commerce browser regressions. Commerce verification correctly hit the Phase 3 reconciliation lock because its fixture reused an already reconciled bank. The fixture now creates its own bank; the production guard was preserved. Browser verification also reports actual API errors directly.
- Final financial review found missing quote enforcement for direct FX confirmation and silently repriced vendor-payment approvals. Quotes now require canonical exact identities for FX, survive decimal-scale database round trips, and remain frozen through approval. Changed rates/carrying values reject approval without posting. Legacy pending approvals lacking a quote must be rejected and resubmitted.
- New focused vendor-payment regression: **4 passed** (missing quote, unconfirmed FX, two changed-carrying-value cases, unchanged approval; parametrization included). Full verification is being repeated with the additional tests; no completion claim yet.

## Completion checkpoint — 2026-10-21

- **Phase 4 implemented and locally verified; ready for owner review.** Final complete `scripts/verify.ps1` run: **305 PostgreSQL tests, 118 frontend unit tests and 43 Playwright scenarios passed**. Django, migration drift, Ruff, OpenAPI (zero warnings), ESLint, strict TypeScript and production build passed. A final focused quote suite also passed 4 tests after exact canonicalization.
- Browser run: `mateerp_e2e_c58242b6601e472fbf3b07d3bbc981d2`; database/files retained, isolated backend stopped. Normal MateERP backend and healthy database remain running. Both storage volumes preserved.
- Normal production build restored and verified to proxy to 8100. Development data unchanged: 59 users, one company, zero queried journal/customer/invoice/payment/bill/expense/filed-document records. Prototype Git working tree clean. Main/HEAD/remote unchanged; whitespace check passed. No commit, push, deployment or Phase 5 development.
- Reviewed Sales/Purchases light/dark/compact screens, invoice detail, explorers, mobile layout/loading state and all official PDF layouts/continuation pages. No pixel-identity guarantee is claimed. Source and workflow fidelity use existing tokens and primitives.
- Final report: `docs/phase-04-summary.md`. Known limits: bounded reference pickers/recent purchase history, operator-configured recurrence scheduling, retained E2E storage, and safe conflict/review for legacy unfingerprinted credit requests or pending vendor approvals without quotes. No fake notifications, data, malware scanning, email or payment gateway.
- **Next action: owner reviews Phase 4 and commits/pushes if accepted. Do not start Phase 5 without explicit approval.** Suggested commit: `feat(commerce): complete Phase 4 billing, expenses and private documents`.
