# MateERP — conventions for Codex sessions

MateERP is NetaMate's commercial ERP. This repository is the **production application**.

## Repositories
- **Production (this repo):** `C:\Users\Rizwan\Desktop\MateERP` · github.com/rizwansammo/MateERP
- **Prototype (read-only design reference):** `C:\Users\Rizwan\Desktop\MateERP-UI` · github.com/rizwansammo/MateERP-UI
  - The prototype is the authoritative **visual and workflow** specification. Never modify it.
  - **Never copy prototype source code.** Reimplement with production architecture. Only approved brand assets (the Astro font and the wordmark reference) are reused.

## Git workflow (permanent rule)
- Work directly on `main`. Do not create feature branches, PRs or merge workflows unless the user explicitly asks.
- **Never commit or push.** At the end of a phase, give the user a suggested commit message. If the user ever asks for a commit or push: add no co-author or attribution lines, and use only their account.
- Never commit secrets (`.env` and `frontend/tests/e2e/.auth/` are gitignored). Never modify other repositories.

## Design fidelity (non-negotiable)
- Match the prototype as closely as possible, ideally pixel for pixel. Do not redesign.
- Use the tokens in `frontend/src/styles/tokens.css` and the components in `frontend/src/components/ui`. Values are documented in `docs/design-reference.md`.
- **Sharp corners only.** The radius scale is empty; never add rounded utilities.
- Sidebar is 264px expanded and 64px compact, background `#0A0F16`, cyan `#00B0F0`, 56px header, IBM Plex Sans 13px.
- Features that are not built yet must say so, with their phase number. No fake data, actions or success messages.

## Architecture
- **Single company, single tenant, modular monolith.** One deployment = one company (a singleton `CompanyProfile`, enforced by a DB constraint). No multi-company, no tenants, no microservices.
- MateERP (the software brand) ≠ the customer company's identity (name, logo, invoice branding, signature, seal).
- **Backend** (`backend/apps/`):
  - `core`: errors, logging, request id, pagination, trusted-proxy client IP, append-only trigger function
  - `accounts`: users, roles, permissions, auth, throttle
  - `company`: profile, business settings, modules
  - `files`: private storage and access policy
  - `branding`: draft and immutable versions
  - `approvals`: policies, requests, executors
  - `audit`: append-only events
  - `accounting`: account hierarchy, periods, immutable posted journals, posting identities, rates, tax mappings, reports
  - `banking`: cash/bank metadata, treasury adapters, statements and reconciliation; no separate ledger
  - `sales` / `billing`: customers, orders, projects, invoices, verified collections, credits and recurrence
  - `purchasing` / `documents`: vendors, bills, expenses, payments and private financial documents
- Business rules live in `services/`; views and serializers stay thin; multi-row changes use `transaction.atomic()`.
- **Frontend:** Next.js App Router + strict TypeScript + Tailwind v4.
  - The browser only calls `/api/v1/*` on its own origin; Next proxies it to Django.
  - `(shell)/layout.tsx` checks the session server-side; `src/proxy.ts` redirects requests with no session cookie.
- **API:** versioned `/api/v1/`. Errors always use `{"error": {code, message, details, request_id}}`. Default permission is `IsActiveUser` (authenticated, active, no pending forced password change).
- No HR or payroll (that is MateHR). No dependency on MateCRM or MateDesk.

## Security conventions (Phase 2)
- **Sessions:** server-side, cookie `mateerp_session` (HttpOnly). CSRF via the `mateerp_csrftoken` cookie and the `X-CSRFToken` header, enforced on *every* unsafe request, including anonymous login (`apps.accounts.authentication.SessionAuthentication`).
- **Permissions:**
  - Stable codes live in `apps/accounts/catalog.py`. Check them with `requires()`, `requires_any()` or `require()` from `apps.accounts.authorization`.
  - Codes are evaluated from the DB on every request.
  - The UI's `can()` is a hint only.
- **Anti-escalation:** a user can only grant, assign or manage access they hold. The last active Administrator cannot be deactivated or demoted. The Administrator role is locked.
- **Private files:** go through `apps.files.services.store_image` (content validation and re-encoding) and are read only via `GET files/<id>/content/`. Access is checked by `apps.files.access.can_read` (purpose- and reference-based, default deny, 404 when hidden). New file purposes need an explicit policy.
- **Audit:** use `apps.audit.services.record()`. Never pass passwords, tokens or temporary credentials. `before`/`after` values are redacted anyway. Audit events and published branding versions are append-only at the DB level (triggers).
- **Approvals:** domain actions call `approvals.services.approval_required()` and `submit()`. Approved requests run the executor registered with `register_executor()`, inside the same transaction.
- **Financial history guard:** `company.services.financial_history_exists()` queries posted journals. Base currency and fiscal start lock after posting; existing fiscal structures also prevent an implicit fiscal-calendar change.

## Financial integrity rules (Phase 3 onward)
- One accounting engine is the single authoritative posting system. No parallel ledgers.
- Use `apps.accounting.services.posting.post_journal()` for domain adapters; never insert a posted journal or write balances. See `docs/accounting-contract.md` for the exact contract and invariants.
- Acquire the company financial lock before settings, approval, journal, period, account and reconciliation locks. Financial writes are atomic. PostgreSQL guards independently enforce posted immutability, balance and period/hierarchy integrity.
- Amounts use NUMERIC(24,6), rates NUMERIC(30,12), actual currency minor units and ROUND_HALF_UP conversion. Rate direction is base units per foreign unit. Foreign bank outflows use historical weighted-average carrying value; chronological posting and sufficient units are required.
- Manual/opening/adjustment/reversal policies freeze snapshots. Approvers need `accounting.approve` + `accounting.manage` + `finance.view`; close/reopen additionally needs `accounting.periods.manage`. New sensitive codes are not silently granted to existing non-admin roles.
- Money: `Decimal` / `NUMERIC` only, never float. The API returns decimals as strings; the frontend formats integer minor units.
- Posted journals balance, are never silently edited, and are corrected only by traceable reversals or adjustments.
- Periods lock. Financial actions are idempotent. Founder personal settlements stay outside company obligations.
- Issued invoices and receipts reference the `BrandingVersion` they were issued with (`features/documents/*` render them).

## Phase 4 conventions
- Apps `sales`, `billing`, `purchasing` and `documents` own customers/projects/orders, AR/collections/credits, AP/expenses and private financial filing respectively. Purchase orders are Phase 6.
- Registered domain adapters obtain actor/source/action-scoped `PostingAuthority`; never expose it through serializers or add a public accounting bypass. Source-owned reversals go through their domain.
- Acquire the company financial lock first. Persist source, number, journal and frozen snapshot atomically. Repeated financial requests compare canonical payload fingerprints; changed payloads conflict.
- A customer payment recorder cannot verify their own payment. Pending verification/approval cannot post cash or generate an official receipt. Credit notes and cash refunds are distinct.
- AR, AP and customer-credit source balances independently reconcile to GL controls. Never add a second ledger or bank balance cache. Historical FX/carrying values and period/reconciliation guards still apply.
- Issued records and their first ready PDFs are immutable. PDF failure is retried against the frozen snapshot without duplicate issuance/posting. Never regenerate ready historical files from current branding.
- Financial uploads use the validated PDF/image storage service, private purpose/reference access and explicit bank-evidence permission. No malware scanning is claimed. Generated PDFs are automatically filed; multi-invoice receipts share one retained file across invoice-year bundles.
- Recurrence is schedule/date-idempotent. Default invoices and all expenses generate drafts. Recheck explicit auto-issue authority and current owner permissions. No background service or OS task is installed implicitly.
- Project profitability uses posted historical base-currency GL costs/revenue across currencies, excluding recoverable tax/capital assets. Issued project billing locks financial identity.
- Browser financial fixtures run only through `scripts/e2e.ps1` in fresh isolated databases on backend 8101, never the development installation. Retain checkpoints in `docs/phase-04-progress.md` and record actual results.

## Phase 5 conventions
- `company.FinancialParty` identifies founders, shareholders and partners, with optional ERP accounts. Never seed real participants, legal shares or balances.
- `founders` owns corporate source records, exact liabilities and allocations, separate personal sharing/confirmed transfers, immutable forecasts and verified-funding designations. `ownership` owns provisional agreement amendments and documented formal register events.
- Corporate posting uses the registered `founder_transaction` authority and the central ledger. A recorder cannot verify their own transaction. Reclassification/reassignment preserves one original obligation per source and its `recovery_origin`; recovery limits apply across the entire split/reclassification history.
- Personal payments never silently clear company liabilities. Overlapping recovery blocks reimbursement until a confirmed return or an explicitly authorized, independently verified and audited corporate resolution exists.
- Equal/custom/provisional/formal sharing policies are effective-dated. Allocation snapshots remain frozen. Promises, forecast targets, reserve designations and personal transfers never create GL cash or expenses.
- Forecasts reuse actual recurrence identities, exact tax and FX helpers. New source selection or policy changes create new snapshots. Reserve consumption links actual posted payments; partial use/releases and retained-funds rollover are audited and never duplicate cash.
- Provisional 50:50 → 40:40:20 amendments do not issue formal units. Formal transfers/issuances require frozen evidence, affected-party consent, distinct independent governance votes and explicit documented confirmation. Linked shareholders act as themselves; external attestations identify the authorized operator and evidence.
- New sensitive permissions are reviewed explicitly; existing non-admin grants are not silently expanded. Private founder/personal/ownership evidence is purpose/reference scoped. General journal responses mask founder identity dimensions unless authorized, without altering financial totals.
- Preserve the Phase 5 checkpoints and use isolated E2E fixtures only. Phase 6 has owner approval; Phase 7 requires separate owner review and approval.

## Roadmap
1. Foundation ✅ · 2. Auth & Administration ✅ · 3. Core Accounting Engine completed · 4. Billing, Expenses & Documents implemented · 5. Founder Finance & Ownership implemented and verified · 6. Operations & Reporting implemented and locally verified (acceptance reports in docs) · 7. Security, Final Testing & Release pending owner approval.

Work on one phase at a time and stop for user review at the end of each phase.

## Local environment (Windows)
- **Docker Compose project `mateerp` only:**
  - Containers `mateerp-db` and `mateerp-backend`; volumes `mateerp-pgdata` and `mateerp-storage`.
  - Loopback ports: DB 55432, API 8100. The frontend runs natively on 3100.
  - Never touch other projects' containers.
  - Optional `e2e` profile: `mateerp-backend-e2e` on loopback 8101, using a fresh `mateerp_e2e_<uuid>` database in the same PostgreSQL server. Never aim browser fixtures at the development database. Run `scripts/e2e.ps1`; keep port 3100 available.
- **No destructive operations:** never `docker compose down -v`, volume removal, DB drop or flush. pytest uses its own `test_mateerp` DB.
- **First administrator:** `docker compose exec backend python manage.py create_admin`
- **All checks:** `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`. See `docs/development.md`.

## Testing expectations
- Every change ships with tests.
  - Backend: pytest against real PostgreSQL in the container.
  - Frontend: Vitest and Playwright through `localhost:3100` against an isolated per-run backend/database. The guarded e2e setup changes only test accounts and test settings. Each run retains its database and files for inspection; it never resets development data.
- Never claim a check passed without running it.


## Phase 6 conventions

- `catalog` extends existing BillingItem IDs with tracked/nonstock/service profiles,
  units, categories and append-only dated prices. Apply a server quote explicitly;
  never silently reprice saved documents or use JavaScript money calculations.
- Procurement owns frozen PO revisions, independent approvals, receipts/service
  acceptance, exact bill matching, retained evidence, acquisition cost corrections
  and supplier-accepted unmatched returns. Goods post Inventory/GRNI; matching
  clears GRNI once. Supplier returns retain original consideration/FX, remove stock
  at weighted-average cost and disclose an authorized cost variance. Posted/settled
  bill consideration must be corrected through its owning workflow first.
- Inventory uses company-wide weighted-average value with location quantities.
  Company lock first; no negatives, no unsupported retroactive recosting. Transfers
  have two retained legs and no GL effect. Counts/cost-only corrections freeze their
  stock basis, obey approval policy and retain original-event links. Cost-only
  corrections additionally need accounting.manage; never use them to hide GRNI/AP.
- Dispatch is company-owned transit. Contract evidence defines transfer of control;
  that explicit event recognizes stock COGS and contract revenue, using unbilled or
  deferred clearing as appropriate. Invoicing, control and returns have distinct
  source identities. Legacy Phase 4 invoice behavior remains unchanged. Credits do
  not automatically restock goods; returns use their original fulfillment cost.
- Assets claim real posted acquisition debits without repeating AP/cash. Frozen
  historical/native cost, prospective straight-line estimates and actual monthly
  charges are separate. Disposal reclassifies actual asset-sale invoicing, without
  collecting cash again. Unused capitalization may be reversed before depreciation;
  retain every record and release the claim only from the permitted reversal date.
  Replacement claims/acquisition reversals cannot predate retained claim releases.
- Budgets use immutable independently approved revisions and nonoverlapping scopes.
  Actuals come from posted GL: operating/COGS, fixed-asset additions net of genuine
  capitalization reversals (not disposal proceeds), and recoverable tax separately.
  Cost-center/project analytical overlays are append-only and do not rewrite source
  financial identity or founder sharing. Funding plans remain forecasts.
- Historical onboarding records original dates/payment source/currency/evidence
  without GL. Reconstruction, opening-only cutover and links to existing verified
  sources are mutually exclusive reviewed dispositions. Pre-registration evidence
  never automatically creates corporate expenses, capital or liabilities. Preserve
  original and recognition dates, historical FX, period/reconciliation restrictions,
  independent adoption and participant-scoped personal evidence.
- Reports/dashboard read owning sources and posted GL, keep currencies separate,
  disclose unallocated aging/cash activity and opening-only provenance, and export
  bounded formula-safe CSV. Cash classification is append-only, with operating,
  investing, financing, opening/cutover and unclassified amounts reconciling to GL.
- Continue isolated browser testing on 8101 only. Keep exact checkpoints in
  docs/phase-06-progress.md. No scheduler/infrastructure is installed implicitly.
  Phase 7 requires owner review and approval after the Phase 6 acceptance report.
