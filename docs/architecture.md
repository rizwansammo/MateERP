# MateERP architecture

## Deployment model
**Single company, single tenant, modular monolith.**
- Each customer company gets its own installation, PostgreSQL database and private document storage. Nothing is shared between companies.
- The company itself is a singleton (`CompanyProfile`, primary key pinned to 1 by a check constraint).
- Branches, departments, projects, locations and cost centres are ordinary data, not tenants.
- Out of scope: multi-company switching or consolidation, shared-tenant schemas, microservices, and HR or payroll (handled by MateHR).

## Runtime topology

```
Browser ──> Next.js (frontend, :3100) ──/api/*──> Django + DRF (backend, :8100) ──> PostgreSQL (:55432)
                │  src/proxy.ts: no session cookie → /login                │
                │  (shell)/layout.tsx: validates the session server-side   └──> private storage volume (mateerp-storage)
```

- The browser only ever talks to the Next.js origin. `next.config.ts` rewrites `/api/*` to Django, so there is no CORS surface and cookies stay first-party.
- In production, a reverse proxy terminates TLS in front of both services (Phase 7).

## Backend (`backend/`)

| App | Responsibility |
|---|---|
| `config/` | Environment-driven settings (`base`, `dev`, `test`, `prod`; prod fails fast on weak or missing secrets), `/api/v1/` routing, OpenAPI |
| `apps/core` | Error envelope, request-id middleware and JSON logging, pagination, `client_ip` (trusted-proxy aware), the shared append-only trigger function |
| `apps/accounts` | `User`, `Role`, `Permission` catalogue, `LoginFailure`; sign-in, sessions, passwords, user and role administration; `create_admin`, `clear_login_locks` |
| `apps/company` | Singleton `CompanyProfile`, `BusinessSettings` (currency display, tax config, numbering), `ModuleSetting`; reference data |
| `apps/files` | `StoredFile` in private storage; validated image uploads; purpose-based read policy |
| `apps/branding` | `BrandingDraft` (editable) and `BrandingVersion` (immutable, numbered); publish and restore |
| `apps/approvals` | `ApprovalPolicy` per category, `ApprovalRequest` with a payload snapshot; executor registry |
| `apps/audit` | `AuditEvent`, append-only; `record()` with redaction |
| `apps/accounting` | Account hierarchy, fiscal years/periods, journal posting/reversal/approval, idempotency, rate history, tax mappings and posted-ledger reports |
| `apps/banking` | Bank/cash metadata linked to GL accounts, treasury adapters, bank statements, exact match groups and reconciliation evidence; no independent ledger |

**Conventions for domain apps**
- Shape: `models.py`, `services/` (business rules and transactions), `api/` (thin views and serializers), `tests/`.
- Domains talk through services. Cross-app hooks use registries (file-reference resolvers, approval executors) wired in `AppConfig.ready()`.
- Services own `transaction.atomic()`; `ATOMIC_REQUESTS` is off. When a failure must still be audited (failed sign-in, denied approval), the audit row is written outside the rolled-back transaction.

**API conventions**
- Versioned under `/api/v1/`, with page-number pagination (`?page=&page_size=`, max 100) returning `{count, page, page_size, total_pages, results}`.
- Errors use `{"error": {code, message, details, request_id}}`. Stable codes include `not_authenticated` (401), `csrf_failed`, `permission_denied`, `password_change_required`, `invalid_credentials`, `too_many_attempts` (429 + `Retry-After`), `validation_error`, `company_exists`, `last_administrator`, `approval_already_pending`.
- The OpenAPI schema validates with zero warnings (`manage.py spectacular --validate --fail-on-warn`).

## Security model (Phase 2)

### Authentication and sessions
- **Server-side sessions in PostgreSQL:**
  - Login rotates the session key. Logout flushes it.
  - Default: browser-session cookie with a 12-hour sliding idle timeout. "Keep me signed in" extends this to 14 days.
  - Cookie `mateerp_session` is HttpOnly and SameSite=Lax (Secure in prod). No tokens are stored in the browser.
- **CSRF:**
  - Django's double-submit check (`mateerp_csrftoken` cookie plus `X-CSRFToken` header) and Origin verification against `CSRF_TRUSTED_ORIGINS`.
  - The custom `SessionAuthentication` enforces CSRF on **every** unsafe request, including anonymous sign-in. DRF's default only checks authenticated requests, which would leave login CSRF open.
- **Password change:** keeps the current session (with a new key) and invalidates all others through Django's session-hash check.
- **Deactivation:** effective on the next request, because inactive users never load as the session user.
- **Temporary passwords:** created by administrators. They are shown once, hashed at rest and never logged. `must_change_password` blocks every endpoint except session, me, password and logout.
- **First administrator:** `manage.py create_admin`, interactive or `MATEERP_ADMIN_PASSWORD`. It refuses to run when an active administrator exists unless given `--force-additional`.

### Sign-in abuse protection
Sliding windows over `LoginFailure` rows; no Redis:

| Scope | Rule | Effect |
|---|---|---|
| Identifier + IP | 5 failures within 15 min | Backoff 1, 2, 4 … 15 min for that pair only |
| Identifier, any IP | > 20 failures per hour | Attempts spaced 30 s apart (never a hard lock) |
| IP, any identifier | 50 failures within 15 min | Address blocked for 15 min |

- Unknown identifiers behave identically, and messages are generic, so accounts can't be enumerated. The password hasher always runs.
- The client IP is `REMOTE_ADDR`. `X-Forwarded-For` is used only when the connecting hop is in `MATEERP_TRUSTED_PROXIES`, taking the right-most untrusted entry. In production, add the reverse proxy's address there.
- Recovery: automatic expiry, `manage.py clear_login_locks`, and an administrator's password reset (which clears that user's failures).

### Authorisation
- **Permission codes:** stable codes in `apps/accounts/catalog.py` (administration, finance, founder, operations), synced after every migrate. Phase 3 adds `accounting.approve` and `accounting.periods.manage`; existing non-admin/custom grants are preserved. Default roles: Administrator (locked; always every permission), Finance Manager, Accountant, Operations Manager, Viewer.
- **Evaluation:** permissions are read from the database on every request, so role and permission changes take effect immediately. Nothing is cached in the session or trusted from the client.
- **Anti-escalation:**
  - You can only grant or revoke permissions you hold, and only assign roles whose permissions you hold.
  - You can only manage users with no more access than you, and you cannot change your own role.
  - The last active Administrator cannot be deactivated or demoted (`select_for_update` serialises the check). Roles with active users cannot be deactivated.
- **Server-side enforcement:** every endpoint uses `IsActiveUser` plus `requires(...)` or `requires_any(...)`. The frontend's `can()` only shapes the UI.

### Private files
- **Uploads:** PNG, JPEG or WEBP only. Each upload is verified and decoded by Pillow (≤ 2 MB, ≤ 4000 px, decompression-bomb guard), then **re-encoded**, which drops metadata and any trailing payload. SVG is rejected.
- **Storage:** server-generated paths (`<purpose>/<uuid>.<ext>`) on the private `mateerp-storage` volume. Files are immutable; replacing an asset creates a new file, so history keeps exactly what it used.
- **Reads:** only through `GET /api/v1/files/<id>/content/`, checked by `files.access.can_read`. Default deny; hidden or unknown files return 404.
  - **Company logo:** any active user while it is referenced (current logo or a branding version); otherwise only branding or company editors.
  - **Signature and seal:** only users with `branding.manage`.
- **Response headers:** `private` cache, `nosniff`, a sandbox CSP and same-origin CORP.

### Audit
- `AuditEvent` stores:
  - who acted, plus an actor-label snapshot
  - the dotted action code and its category
  - the target
  - request id and client IP
  - redacted before/after values
  - outcome and reason
- **Append-only:** a PostgreSQL trigger rejects UPDATE and DELETE, and there is no write API. `audit.view` is required to read.
- **What is recorded:** sign-ins (success, failure and throttling), logout, password changes and resets, user and role changes, permission changes, company and logo changes, business-settings and module changes, branding draft and publication events, and approval requests and decisions (including denied attempts).
- **Never recorded:** credentials. Unknown sign-in identifiers are not stored verbatim.

## Branding versioning
- Workflow: **Edit → Preview → Save draft → Publish.** The singleton draft is freely editable and never affects documents.
- Publishing creates a numbered `BrandingVersion` that freezes:
  - the configuration
  - a snapshot of the company identity
  - the invoice and receipt number formats
  - the exact logo, signature and seal files (PROTECT foreign keys)
- Versions are immutable at the database level. Restoring an old version publishes a new one (`restored_from`); history is never rewritten.
- Phase 4 invoices and receipts must store the version they were issued with and render through `frontend/src/features/documents/*` (Meridian, Ledger or Atlas invoices; Official or Compact receipts), so their appearance never changes.

## Approvals
- One `ApprovalPolicy` per category: sensitive administrative changes, expenses, purchase orders, client payments, financial adjustments, ownership changes.
- Each policy has: required/active flags, a designated approver role, an optional amount threshold, a self-approval flag and notes.
- **Enforced now:** branding publication and financial adjustments (manual/opening/adjustment journals, bank adjustments and reversals). Internal bank transfers cannot inject arbitrary adjustment lines and use their own posting source. Thresholds use total base debit once. Exact financial snapshots are frozen and verified again by the executor; approval and posting commit together.
- **Rules:** one pending request per `(action, subject_key)`, enforced by a partial unique index. Branding keeps its empty singleton subject; different journals may await approval together. Financial approvers need finance read, accounting management and financial approval permissions as well as designated-role/self-approval checks. Status consistency is enforced by a check constraint.
- **Other categories:** stored now; their modules enforce them when they ship. The UI states this honestly.

## Modules and settings
- **Optional modules:** founder finance, ownership, procurement, inventory, fixed assets, budgeting.
  - `ModuleSetting` is the server-side source of truth (`company.services.is_module_enabled`).
  - Disabled modules are hidden from navigation and never deleted.
  - Enabled-but-unbuilt modules stay labelled "Planned · Phase N".
- **Currency and tax:** effective-dated FX and tax-account revisions exist in Phase 3. Posted lines retain snapshots. Billing tax calculation is Phase 4; tax filing is outside scope. `financial_history_exists()` queries posted journals; the service and PostgreSQL both lock company base currency/fiscal start after posting.
- **Number formats:** tokens `{YYYY} {YY} {MM} {###…}`, exactly one sequence token, and a distinct letter prefix per document type. Sequential issuance arrives with each document module.

## Frontend (`frontend/src/`)

| Path | Responsibility |
|---|---|
| `proxy.ts`, `app/(shell)/layout.tsx`, `lib/auth/*` | Route protection, session bootstrap, `AuthProvider` (`can`, preferences, sign-out, session-expiry redirect), safe `?next=` handling |
| `lib/api/client.ts`, `lib/api/query.ts` | Typed client (CSRF, retry once on `csrf_failed`, 401 → expired session) and a small shared query cache with prefix invalidation |
| `components/ui/` | Design system: Button, inputs, Drawer, Modal, ConfirmDialog, Toast, InfoPanel, Banner, Segmented, FileDrop, table kit, Restricted, StatGrid … |
| `components/shell/` | Sidebar (real company card, module-aware and permission-aware navigation), Header (account menu, approval notifications, theme) |
| `features/auth` | Sign-in and password screens |
| `features/settings/*` | Company, branding (overview, studio, version viewer), users and roles, permissions, approvals, modules, financial/currency/tax, audit, preferences, about |
| `features/documents/*` | Invoice and receipt templates, SVG company seal, integer-minor-unit money helpers |
| `features/accounting/*` | Ten accounting/banking screens, exact BigInt money helpers, journal/opening editors, treasury preview, reconciliation, rates/tax/period controls and reports |

Personal preferences (theme, sidebar, rows per page, landing page) are stored on the user and mirrored to the pre-paint localStorage cache, so first paint never flashes.

## Domain boundaries

| Domain app | Phase | Owns |
|---|---|---|
| `accounting`, `banking` | 3 (implemented) | Central journals and reports; bank/cash adapters and reconciliation |
| `sales`, `purchasing`, `documents` | 4 | Customers, invoices, payments, receipts, credit notes; vendors, bills, expenses, POs; document storage |
| `founders`, `ownership` | 5 | Contributions, founder-paid expenses, sharing policies, settlements, loans; shareholders, capital, transfers |
| `inventory`, `assets`, `budgeting`, `catalog`, `reporting` | 6 | Stock, valuation, fixed assets, depreciation, budgets, cost centres, catalogue, statements |

### Financial integrity (Phase 3)

The implemented contract and database invariants are documented in [accounting-contract.md](accounting-contract.md). All financial writes acquire the company-row mutex first, then domain locks, inside a database transaction. This deliberately simple single-instance strategy serializes financial changes; it is an explicit throughput tradeoff, not an application-side balance cache.

`post_journal()` is the internal domain adapter entry point; `post_draft()` is the reviewed draft workflow. Public requests carry a `posting_key` JSON field and cannot set trusted source identities. Unique keys, source actions, reversal targets and journal numbers prevent duplicates. Draft revisions reject stale edits. Posted journal headers and lines are immutable; a deferred PostgreSQL trigger requires at least two lines and exact equality of **base-currency** debits and credits. Native amounts need valid minor units, but cross-currency entries need not balance separately in each native currency.

Amounts use `NUMERIC(24,6)`, rates `NUMERIC(30,12)`, Python Decimal and explicit ROUND_HALF_UP conversion. Frontend amounts remain strings and BigInt minor units. Foreign bank credits remove weighted-average historical book value; disclosed realized differences use configured FX gain/loss controls. Unvalued foreign overdrafts and backdated foreign movements are rejected. Exact reversals retain original native/base values and rates.

PostgreSQL independently guards period containment/overlap, closing, financial history, hierarchy meaning, statement completion and consumed reconciliation memberships. Reports include posted entries only. Running ledger balances are SQL-windowed before search/page slicing; multi-query statement reports hold the financial mutex for a coherent snapshot. Hierarchy rows are display subtotals, excluded from grand-total arithmetic.

Founder personal settlements remain outside company obligations. Future financial documents reference immutable branding versions and use this posting engine. No Phase 4 document issuance is included here.

## Key decisions

| Decision | Reason |
|---|---|
| Django 5.2 LTS | Supported until April 2028; move to 6.2 LTS when it ships |
| TypeScript 5.9, ESLint 9 | Most stable with the Next.js 16 toolchain today |
| Same-origin API proxy, no CORS | Smaller attack surface; first-party session cookies with CSRF |
| Session auth, not tokens | HttpOnly server sessions can be revoked centrally; nothing sensitive in browser storage |
| Custom `User` with one role FK | Simple, auditable RBAC; Django groups and permissions are unused |
| DB triggers for append-only tables | History cannot be rewritten even by buggy or compromised application code |
| DB-backed throttle, no Redis | Single-instance architecture; durable and testable; no new infrastructure |
| Re-encoding uploads | Neutralises polyglots and metadata leaks instead of trusting declared types |
| Self-hosted fonts and icons | No runtime third-party requests from a financial application |
| Django admin not installed | Administration happens through the audited application UI |

## Roadmap
1. **Project foundation:** complete
2. **Authentication and administration:** complete
3. **Core accounting engine:** implemented; see Phase 3 acceptance report
4. Billing, expenses and documents
5. Founder finance and ownership
6. Business operations and reporting
7. Security, final testing and release
