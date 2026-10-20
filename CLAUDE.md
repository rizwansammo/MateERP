# MateERP — conventions for Claude Code sessions

MateERP is NetaMate's commercial ERP. This repository is the **production application**.

## Repositories
- **Production (this repo):** `C:\Users\Rizwan\Desktop\MateERP` · github.com/rizwansammo/MateERP
- **Prototype (read-only design reference):** `C:\Users\Rizwan\Desktop\MateERP-UI` · github.com/rizwansammo/MateERP-UI
  - The prototype is the authoritative **visual and workflow** specification. Never modify it.
  - **Never copy prototype source code.** Reimplement with production architecture. Only approved brand assets (Astro font, wordmark reference) are reused.

## Design fidelity (non-negotiable)
- The UI must match the prototype as closely as possible, ideally pixel for pixel. Do not redesign.
- Use the tokens in `frontend/src/styles/tokens.css` and the components in `frontend/src/components/ui`. Values are documented in `docs/design-reference.md`.
- **Sharp corners only.** The radius scale is empty; never add rounded utilities.
- Sidebar is 264px expanded and 64px compact, background `#0A0F16`, cyan accent `#00B0F0`, 56px header, IBM Plex Sans 13px base.
- Features that are not built yet must say so (phase number). No fake data, no fake success messages.

## Architecture
- **Single company, single tenant, modular monolith.** One deployment = one company, with its own database and private document storage. No multi-company or shared-tenant designs, no microservices.
- MateERP (software brand) ≠ the customer company's identity (name, logo, invoice branding, signature, seal).
- **Backend:** Django + DRF + PostgreSQL in `backend/`. Domain apps live in `backend/apps/<domain>/` and are created when their phase starts. Business rules go in `services/`, not in views, serializers or models.
- **Frontend:** Next.js App Router + TypeScript (strict) + Tailwind v4 in `frontend/`. The browser calls only `/api/v1/*` on its own origin; Next proxies it to Django.
- The API is versioned (`/api/v1/`). Every error uses the envelope `{"error": {code, message, details, request_id}}`. Endpoints require authentication by default.
- No HR or payroll (that is MateHR). MateERP must not depend on MateCRM or MateDesk.

## Financial integrity rules (apply from Phase 3 onward)
- One accounting engine is the single authoritative posting system. No parallel ledgers.
- Money: `Decimal` / `NUMERIC` only, never float. The API serialises decimals as strings.
- Posted journals must balance, are never silently edited, and are corrected only by traceable reversals or adjustments.
- Periods can be locked. Financial actions are idempotent. Multi-row changes run in explicit DB transactions.
- Reconciliation keeps auditable links. Founder personal settlements stay separate from company obligations.
- Issued invoices and receipts keep their historical branding and stable document identities.

## Roadmap
1. Foundation (done) · 2. Auth & Administration · 3. Core Accounting Engine · 4. Billing, Expenses & Documents · 5. Founder Finance & Ownership · 6. Operations & Reporting · 7. Security, Final Testing & Release.
Work on one phase at a time. Stop for user review at the end of each phase.

## Git workflow
- Work directly on `main`. Do not create branches or pull requests unless the user explicitly asks.
- **Never commit or push.** At the end of a phase, give the user a suggested commit message. If the user ever asks for a commit or push: no co-author or attribution lines, and use only their account.
- Never commit secrets (`.env` is gitignored). Never modify other repositories.

## Local environment (Windows)
- Docker Compose project `mateerp` is isolated from other local projects: containers `mateerp-db` and `mateerp-backend`, volume `mateerp-pgdata`. Ports bind to 127.0.0.1 only: DB on 55432, API on 8100. Frontend runs natively on 3100. Never touch other projects' containers.
- Run all checks with `powershell -File scripts/verify.ps1`. See `docs/development.md`.

## Testing expectations
- Every change ships with tests. Backend: pytest against real PostgreSQL inside the container. Frontend: Vitest unit tests and Playwright e2e against the live backend.
- Never claim a check passed without running it.
