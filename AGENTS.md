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
- **Financial history guard:** `company.services.financial_history_exists()` is always False until Phase 3. Phase 3 must implement it so base currency and fiscal year become locked.

## Financial integrity rules (Phase 3 onward)
- One accounting engine is the single authoritative posting system. No parallel ledgers.
- Money: `Decimal` / `NUMERIC` only, never float. The API returns decimals as strings; the frontend formats integer minor units.
- Posted journals balance, are never silently edited, and are corrected only by traceable reversals or adjustments.
- Periods lock. Financial actions are idempotent. Founder personal settlements stay outside company obligations.
- Issued invoices and receipts reference the `BrandingVersion` they were issued with (`features/documents/*` render them).

## Roadmap
1. Foundation ✅ · 2. Auth & Administration ✅ · 3. Core Accounting Engine · 4. Billing, Expenses & Documents · 5. Founder Finance & Ownership · 6. Operations & Reporting · 7. Security, Final Testing & Release.

Work on one phase at a time and stop for user review at the end of each phase.

## Local environment (Windows)
- **Docker Compose project `mateerp` only:**
  - Containers `mateerp-db` and `mateerp-backend`; volumes `mateerp-pgdata` and `mateerp-storage`.
  - Loopback ports: DB 55432, API 8100. The frontend runs natively on 3100.
  - Never touch other projects' containers.
- **No destructive operations:** never `docker compose down -v`, volume removal, DB drop or flush. pytest uses its own `test_mateerp` DB.
- **First administrator:** `docker compose exec backend python manage.py create_admin`
- **All checks:** `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`. See `docs/development.md`.

## Testing expectations
- Every change ships with tests.
  - Backend: pytest against real PostgreSQL in the container.
  - Frontend: Vitest, plus Playwright end-to-end tests against the live stack at `localhost:3100`. The e2e global setup manages `e2e-*` accounts and clears sign-in throttling.
- Never claim a check passed without running it.
