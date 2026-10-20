# Phase 4 — Billing, Expenses & Documents

Implementation resumed from Claude's uncommitted files on `main`, based on Phase 3 commit `ab116a0b6c3860bc813cd40625d65296b466ff39`. Date: 2026-10-21 (Asia/Dhaka).

**Acceptance status: Phase 4 implementation and local verification complete; ready for owner review.** No commit, push, deployment or Phase 5 development was performed.

## Features and files delivered

| Area | Working functionality | Principal files |
|---|---|---|
| Sales | Customers/contacts, projects/milestones, billing items, sales-order confirmation/conversion and real summaries | `backend/apps/sales/`, `frontend/src/features/sales/{Customers,Orders,Projects,Setup,Overview}.tsx` |
| Billing | Exact server tax/discount calculations, draft/approval/issue/void, partial and multi-invoice payments, segregated verification, receipts, credit notes, customer-credit applications and refunds | `backend/apps/billing/`, `frontend/src/features/sales/{Invoices,InvoiceEditor,Payments,Receipts,Credits}.tsx` |
| Purchasing | Vendors/statements, duplicate-reference protection, vendor bills, paid/accrued expenses, reviewed vendor payments, AP history and summaries | `backend/apps/purchasing/`, `frontend/src/features/purchases/` |
| Recurrence | Invoice/expense schedules, pause/resume, due-run generation/history, reviewed drafts, explicitly authorized auto-issue and OS command | `billing/services/recurring.py`, `purchasing/services/recurring.py`, `billing/management/commands/run_recurring.py`, both frontend `Recurring.tsx` files |
| Official documents | Retained Meridian/Ledger/Atlas invoice and credit-note PDFs, Official/Compact receipts, retry after rendering failure | `backend/apps/documents/`, `frontend/src/features/documents/{InvoiceDocument,ReceiptDocument,view,money}.tsx/.ts` |
| Filing | Client invoice-year bundles and vendor year/month folders; search, paging, list/grid, metadata, archive, private upload/view/zoom/fullscreen/download and financial links | `frontend/src/features/filing/{Explorer,UploadDrawer}.tsx`, `features/commerce/FileViewer.tsx`, `documents/selectors.py`, `documents/api/references.py` |
| Integration | Protected catch-all Sales/Purchases routes, two document routes, permission-aware navigation, posting controls/defaults, numbering labels and approval review links | `frontend/src/app/(shell)/`, `lib/navigation.ts`, `features/settings/`, `features/accounting/Accounts.tsx` |

Shared commerce forms, line editors, exact-money helpers, loading/error states, dense tables, charts and record panels reuse the existing design system. Product version is 0.4.0. Purchase orders remain explicitly Phase 6; founder finance/ownership remain Phase 5.

## Backend continuity and corrections

The inherited sales, billing, purchasing and document services were retained. Confirmed gaps were corrected with targeted changes:

- One official multi-invoice receipt is discoverable in every related invoice-year bundle, with distinct file counts and one retained PDF. Payment-only bank proof references follow the same allocation links; explicitly invoice-linked proofs stay specific.
- Credit-note, refund and customer-credit application keys compare canonical request fingerprints. Identical concurrent requests have one financial effect; different payloads conflict. Immutable identities are guarded in PostgreSQL.
- Project margin excludes output tax. Cross-currency costs use historical posted base values, exclude recoverable input tax/capital assets, and link to their source records. Issued project billing locks its customer/currency/contract identity.
- FX confirmation requires a reviewed quote. Vendor-payment approvals freeze and revalidate that quote, reject changed carrying values without posting, and preserve exact quote identity across database decimal-scale changes.
- Fiscal overview series derive from posted ledger lines, retaining originals and dated reversals; charts do not invent monthly data. Aging retains historical AR book value.
- Receipt amount-in-words handling uses exact integer/decimal values, including large amounts. Multi-page PDFs retain all line items and final totals with safe repeated-header margins.
- Filing reference choices are bounded and identity-only, with area permissions. Invalid numeric filters return validation errors rather than server failures. Scheduler dry-run lists both invoice and expense occurrences without creating records.
- Frontend fixes preserve textual tax identifiers, submit asynchronously loaded currency defaults, clear stale calculations, retry issue against the saved draft, and protect edited order/payment forms from accidental dismissal.

## Accounting integrity and reconciliation

The Phase 3 accounting engine remains the sole posting system. Domain-specific `PostingAuthority` cannot be supplied by public API callers. Source-owned reversals and subledger controls cannot be bypassed through manual journal endpoints.

Unissued invoices and unverified/pending-approval payments have no posted financial effect. Issuance posts balanced AR/revenue/tax. Verification settles exact invoice allocations and creates the official receipt. Credit notes, credit applications and cash refunds remain distinct. Vendor bills/accrued expenses post AP; vendor payments settle their original carrying values. Foreign bank outflows retain historical weighted-average valuation and disclosed FX confirmation.

AR, customer-credit and AP source balances are independently reconciled with GL controls. Tests assert zero differences after settlement, credit/refund and FX workflows. Period/reconciliation guards, immutable journals, exact decimals and atomic company-first locking remain enforced.

## PDF and historical branding integrity

Issued documents retain business snapshots, numbers, published branding references and original private-file identities. Browser acceptance hashes the original PDF before and after a new branding publication and asserts identical bytes. Ready PDFs are never regenerated using current branding. Rendering failure can be retried against the frozen snapshot without duplicate posting or numbering.

Automated PDF tests exercise all eight document/layout combinations and 90-line invoices in all three layouts. Raster review covers each layout, repeated headers, continuation pages and final totals. No missing lines or clipped continuation headers remain in reviewed artifacts. These are test documents in isolated storage, not development-company invoices.

## Security, permissions and approvals

All browser requests use the existing same-origin proxy, HttpOnly sessions and CSRF checks. Current database permissions govern server actions. A recorder cannot verify their own customer payment. Approval thresholds/designated roles apply to the actual source workflow; pending approval cannot be treated as posted. Approval UI links reviewers to the relevant financial record.

Private metadata, preview and downloads use purpose/reference authorization. Bank proof additionally requires `banking.evidence.view`; unauthorized metadata and byte requests return 404. Images are validated/re-encoded and PDFs inspected; active/unsafe files are rejected. No malware scanning, email delivery or payment-provider integration is claimed. Audit records preserve attribution without passwords or temporary credentials.

## Verification evidence

Final entry point: `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`.

| Check | Final result |
|---|---|
| Django configuration and PostgreSQL | Passed |
| Applied migrations / migration drift | Applied; no missing migrations |
| Ruff lint / format | Passed; 229 files formatted |
| Full PostgreSQL pytest, including Phases 1–3 | **305 passed** in 170.23 seconds |
| OpenAPI validation with fail-on-warning | Passed; no warnings |
| ESLint / strict TypeScript | Passed |
| Full Vitest suite | **118 passed**, 10 files |
| Next.js production build | Passed (Webpack, strict types) |
| Full isolated Playwright suite | **43 passed** in 4.0 minutes, including all Phase 1–3 browser regressions |
| Git whitespace check | Passed |

The complete verification script finished with **All checks passed**. Additional focused quote/approval tests passed after exact quote canonicalization (4 tests). Earlier focused checks covered credit-request concurrency, project costs, filing and all PDF templates. The combined browser fixture was corrected to use its own bank after the existing reconciliation guard correctly rejected reuse of a previously reconciled Phase 3 bank. No production guard was weakened.

The final browser suite used `mateerp_e2e_c58242b6601e472fbf3b07d3bbc981d2` and test backend 8101; its database/files are retained. Development fixtures are never used for financial acceptance. GitHub CI has not run for these uncommitted changes; its workflow is preserved and includes the required PDF system libraries.

## UI fidelity

Read-only prototype captures cover Sales/Purchases overview, invoices/expenses and both document explorers. Production retains the 264/64px sidebar, 56px header, cyan/dark sidebar colors, Astro wordmark, IBM Plex typography, sharp corners and established density. Overview charts follow the reference grouped/stacked bars, aging strip and vendor bars. Drawers/viewer use existing primitives.

Reviewed production captures cover light/dark/compact overviews, invoices, both explorers and the mobile route/loading layout. Browser assertions verify 264/64px sidebars, 56px header, approved colors, theme persistence and mobile navigation. Pixel-for-pixel identity is not claimed: real permissions, validation, empty states and reconciliation evidence necessarily differ from prototype demonstration content.

## Migrations and environment

New migrations: `accounting.0004–0005`, `accounts.0004`, `company.0002`, `files.0002`, `sales.0001–0002`, `billing.0001–0003`, `purchasing.0001–0002`, `documents.0001–0003`. They add schemas, guards, permissions and sequence/configuration foundations; they do not seed transactions or replace existing development data. The additional credit fingerprint migration is additive; old blank fingerprints are preserved and conflicting legacy replays require record review.

WeasyPrint 70.0 and pypdf 6.21.1 extend the existing supported stack. Pango/Harfbuzz dependencies live in the backend image and CI; no Windows-native PDF service or new infrastructure is required. Only the MateERP Compose project is operated on; existing database/storage volumes are retained.

## Start and operate locally

```powershell
# Repository root; preserve existing environment files and volumes.
docker compose up -d --build backend
docker compose exec backend python manage.py migrate
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3100`. Existing backend/database remain at 8100/55432. Configure unused AR/AP/customer-credit controls, revenue/expense defaults at `/sales/setup`, periods, taxes/FX and published branding before issuance. Customer payments require a separate authorized verifier. See [development.md](development.md) for scheduler commands and PDF recovery.

## Known limits and Phase 5 readiness

- No scheduled OS task is installed automatically. Recurrence runs on demand or through an operator-configured task.
- Form reference pickers are bounded to 100 records; high-volume searchable selection and load/performance testing remain release-readiness work. Purchase history currently returns a bounded recent set, labeled in the UI.
- No OCR, malware scanner, email delivery, payment gateway, customer-facing portal or statutory tax filing is implemented or implied.
- Retained isolated E2E databases/files consume disk; cleanup requires a separate deliberate decision and is never automatic.
- Existing legacy credit requests without a fingerprint cannot be safely replayed as new requests; retain/review their original records. Legacy pending vendor-payment approvals without a frozen quote must be rejected and resubmitted; issued history is preserved.
- Visual review establishes close design fidelity, not an automated pixel-difference guarantee. Financial/authorization regression tests are the acceptance evidence.

Phase 5 can build founder obligations, reimbursements and ownership on the established domain posting and immutable-document contracts after owner review. Personal founder settlements must remain separate from company expenses/liabilities. No Phase 5 work has begun.

## Final Git and Docker state

Final audit: branch `main`, HEAD unchanged at `ab116a0b6c3860bc813cd40625d65296b466ff39`, expected remote unchanged, Git whitespace check passed, and the prototype working tree remains clean. Development counts remain 59 users, one company and zero journals/customers/invoices/payments/bills/expenses/filed documents. `mateerp-backend` and healthy `mateerp-db` are running; `mateerp-backend-e2e` is stopped. Both named data/storage volumes remain present. The final native production build passed and its API rewrites point to 8100. All work is intentionally uncommitted on `main`; no branch, commit, push, force operation, deployment, database reset or volume removal was performed. The confirmed temporary `billing/tests/dump_visual.py` was removed; no broad cleanup was performed. Documentation and both agent instruction files preserve the established project rules.

Suggested commit message:

```text
feat(commerce): complete Phase 4 billing, expenses and private documents
```
