# Development setup (Windows)

## Prerequisites
| Tool | Version used |
|---|---|
| Docker Desktop (Compose v2+) | 29.x / Compose 5.x |
| Node.js | 24 LTS (`>=22.12` required) |
| Git | any recent |
| Python 3.13 (optional) | only for editor IntelliSense; the backend runs in Docker |

All commands below are PowerShell, run from the repository root unless noted.

## 1. Configure the environment
```powershell
Copy-Item .env.example .env
# Edit .env: set POSTGRES_PASSWORD, the password inside DATABASE_URL, and DJANGO_SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(50))"
Copy-Item frontend\.env.example frontend\.env.local
```
`.env` and `.env.local` are gitignored. Never commit them.

## 2. Start the backend stack
```powershell
docker compose up -d --build
docker compose ps
```
This starts the isolated Compose project **`mateerp`**:

| Container / volume | Purpose | Host address |
|---|---|---|
| `mateerp-db` | PostgreSQL 18 (volume `mateerp-pgdata`) | `127.0.0.1:55432` |
| `mateerp-backend` | Django dev server (code bind-mounted, auto-reload) | `127.0.0.1:8100` |
| `mateerp-storage` (volume) | Private file storage: logos, signatures, seals | not exposed |

- Ports bind to localhost only, and the names don't clash with other local Compose projects. Change the host ports in `.env` (`MATEERP_DB_PORT`, `MATEERP_BACKEND_PORT`) if needed.
- Migrations run automatically when the backend container starts. The permission catalogue, default roles, module settings and approval policies are created right after migrating.

## 3. Create the first administrator
MateERP ships with **no default account or password**. Create the first administrator with the management command:

```powershell
docker compose exec backend python manage.py create_admin
# Prompts for username, email and password (entered twice, hidden).
```

Non-interactive alternative (scripted deployments): pass the password through the `MATEERP_ADMIN_PASSWORD` environment variable, filled from your secret store. The command never accepts a password argument, which would end up in shell history.
```powershell
docker compose exec -e MATEERP_ADMIN_PASSWORD backend python manage.py create_admin --no-input --username owner --email owner@example.com
```
(`-e NAME` without a value forwards the variable from your current shell.)

How the command behaves:
- It refuses to run when an active administrator already exists. Use `--force-additional` only for recovery.
- Passwords must pass Django's validators: at least 12 characters, not common, not entirely numeric, and not similar to the username.
- After signing in, create other users in **Settings → Users & roles**. They receive a one-time temporary password that must be changed at first sign-in.

## 4. Start the frontend
```powershell
cd frontend
npm ci
npm run dev        # http://localhost:3100
```
Requests to `/api/*` are proxied to `MATEERP_BACKEND_URL` (default `http://127.0.0.1:8100`). Sign in at http://localhost:3100/login.

## Everyday commands
| Task | Command |
|---|---|
| Backend tests | `docker compose exec backend pytest` |
| Backend lint / format | `docker compose exec backend ruff check .` · `docker compose exec backend ruff format .` |
| OpenAPI check | `docker compose exec backend python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml` |
| New migrations | `docker compose exec backend python manage.py makemigrations` |
| Apply migrations | `docker compose exec backend python manage.py migrate` |
| Clear sign-in throttling | `docker compose exec backend python manage.py clear_login_locks --identifier <username-or-email>` (or `--ip`, `--all`) |
| Django shell | `docker compose exec backend python manage.py shell` |
| Backend logs | `docker compose logs -f backend` |
| Frontend unit tests | `cd frontend; npm test` |
| Frontend lint / types | `npm run lint` · `npm run typecheck` |
| Production build | `npm run build` |
| E2E tests | `npx playwright install chromium` (once), then `npm run test:e2e` (builds automatically; backend must be running and port 3100 available) |
| **Everything** | `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` |
| Stop stack | `docker compose down` (data kept) |

Never use `docker compose down -v`, volume removal, database drop or flush during development or verification. Preserve development data.

## About the end-to-end tests
- `scripts/e2e.ps1` creates a new `mateerp_e2e_<uuid>` PostgreSQL database, using the existing MateERP database server. It starts only the optional `mateerp-backend-e2e` container on loopback 8101 and builds the frontend proxy against it. The browser still uses the real origin `http://localhost:3100`, session cookies and CSRF.
- `config.settings.e2e` rejects database names without the isolated prefix; global setup refuses to run against development settings. Test account, company, branding, accounting and approval fixtures never touch the development database.
- The script stops only the test backend after the run. Its database is retained, with private files at `mateerp-storage:/e2e/<database-name>/`. Run names appear in the output. No automatic deletion is performed. Retained databases consume disk; review them deliberately before any separately authorized cleanup.
- The Playwright state file under `frontend/tests/e2e/.auth/`, screenshots and traces under `frontend/test-results/` are gitignored. Passwords are random per run and not written to source or logs.
- Close your own frontend on 3100 before tests; the runner refuses to adopt an existing server. Focused run from the root: `powershell -ExecutionPolicy Bypass -File scripts/e2e.ps1 -TestFile phase3.spec.ts`.
- After browser tests, `npm run dev` uses the normal 8100 backend. A production test build retains the 8101 rewrite: rebuild with the normal `MATEERP_BACKEND_URL` before using `npm run start` for development.
- `npm run dev` and `npm run build` explicitly select Next.js's supported Webpack bundler. On this Windows environment Turbopack's CSS worker exited unexpectedly, including outside the sandbox; Webpack builds and type validation succeed. No framework downgrade or validation bypass is used.

## First accounting setup

1. Confirm the company base currency and fiscal start before posting. They become locked by history.
2. Use Chart of Accounts → Set up starter chart (explicit preview) or create your own hierarchy. Configure postable FX gain/loss and retained-earnings controls as needed.
3. Create a fiscal year in Accounting Periods; its twelve months are generated from the company's fiscal start.
4. Create bank/cash metadata and link distinct postable asset GL accounts before loading their opening balances.
5. Enter a balanced opening journal at the chosen migration date, with every equity/earnings offset visible. Approval rules apply. There is only one initial opening source; subsequent corrections use linked reversals/adjustments.
6. Foreign currencies need enabled currency settings and an applicable exchange-rate revision. Treasury previews show explicit FX differences; a changed quote requires a fresh preview.

See [accounting-contract.md](accounting-contract.md) for posting, approval, period, reconciliation and history rules. Phase 4 adds invoices, receipts, credits and purchasing. Statutory tax filing remains outside the application.

## Editor support (optional)
Python dependencies live in the container. For IntelliSense, create a local venv (includes `django-stubs` and `djangorestframework-stubs`):
```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\pip install -r requirements\dev.txt
```
Then select `backend\.venv` as the interpreter. `pyproject.toml` points Pyrefly at the venv and disables checks the Django stubs can't express without the mypy plugin.

## Troubleshooting
- **Port already in use:** change `MATEERP_DB_PORT` / `MATEERP_BACKEND_PORT` in `.env` and update `frontend/.env.local`.
- **"Set POSTGRES_PASSWORD in .env":** you haven't created `.env` yet (step 1).
- **"MateERP server unavailable" page:** check `docker compose ps` and `docker compose logs backend`.
- **"Too many sign-in attempts":** wait for the shown delay, or run `clear_login_locks`.
- **"Security check failed" on a form:** the CSRF cookie was rotated (e.g. after signing in elsewhere). The client retries once automatically; reload if it persists.
- **Signed in on another port or host:** add the origin to `DJANGO_CSRF_TRUSTED_ORIGINS` in `.env`.
- **Changed `.env` credentials after the first start:** the database volume keeps the original password. Restore the matching local configuration or arrange a deliberate credential rotation; do not recreate the data volume.


## Sales, purchasing and documents (Phase 4)

For an existing checkout, preserve `.env`, `.env.local`, PostgreSQL and storage volumes. Rebuild only the MateERP backend image for WeasyPrint 70.0, pypdf 6.21.1 and their Pango/Harfbuzz libraries:

```powershell
docker compose up -d --build backend
docker compose exec backend python manage.py migrate
```

The established framework versions are retained. WeasyPrint runs inside Linux Docker; Windows developers do not need a native PDF runtime. Fonts are bundled and the renderer denies arbitrary external URLs.

1. Configure unused postable Receivable, Payable and Customer credit controls in Chart of Accounts. Migrations never relabel balances or grant new sensitive codes to existing non-administrator roles; review role permissions explicitly.
2. Set revenue/expense defaults and billing items at `/sales/setup`. Configure applicable tax revisions and FX accounts/rates.
3. Publish invoice/receipt branding. Issued documents freeze company identity, line/tax values and the published version.
4. Use Sales for customers, orders, projects, invoices, payments, receipts and credits. Customer payments require a different authorized verifier. Pending verification/approval has no posted cash or official receipt.
5. Use Purchases for vendors, bills, accrued/paid expenses and reviewed payments. Foreign-payment previews require explicit confirmation of nonzero disclosed FX differences. Purchase orders remain Phase 6.
6. Client/Vendor Documents file generated PDFs automatically and accept authorized PDF/PNG/JPEG/WEBP evidence up to 10 MB. Bank proofs require evidence permission for metadata and bytes. Archive uploaded evidence with a reason; historical official PDFs remain retained.

PDF failure does not duplicate a successfully issued financial record. Open its detail page and use **Retry PDF**. This renders the frozen snapshot and preserves the first ready PDF. Investigate errors through request IDs and backend logs.

### Recurring schedules

The UI's **Run due** processes selected schedules through today. Windows Task Scheduler can invoke the same services:

```powershell
# Working directory: C:\Users\Rizwan\Desktop\MateERP
docker compose exec -T backend python manage.py run_recurring --dry-run
docker compose exec -T backend python manage.py run_recurring
# Optional controlled catch-up date:
docker compose exec -T backend python manage.py run_recurring --date 2026-10-21
```

Run only against this Compose project and review output for failed occurrences. No scheduler is installed automatically. Repeated/overlapping runs do not duplicate schedule/date occurrences. Default invoice runs and all expense runs create drafts. Auto-issue requires explicit authority that is rechecked at execution. No email or payment-provider action is simulated.

### Phase 4 checks

Run `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`, or `scripts\e2e.ps1 -TestFile phase4.spec.ts` for focused isolated browser scenarios. Tests cover exact tax/discounts, historical FX, settlement, verifier segregation, concurrency, period locks, approvals, reconciliation, immutable PDFs and private evidence. See [Phase 4 summary](phase-04-summary.md) for execution results.

## Phase 5: founder finance and ownership

The existing Docker/native Windows arrangement and supported dependencies are retained. Update only this repository and run:

```powershell
docker compose up -d backend
docker compose exec backend python manage.py migrate
# Restart the API after changing installed apps/settings if it is not watching source changes:
docker compose restart backend
cd frontend
npm run dev
```

1. Review narrow founder, personal-sharing, planning and ownership permissions under Users & Roles. Administrator access includes the new codes; existing non-administrator roles do not silently receive sensitive new grants.
2. Configure unused, correctly typed Founder payable, Founder loan, Pending founder funding, Other founder equity, Share capital and Share premium controls in Chart of Accounts. Historical balances are never relabelled by migrations. Configure real currencies, FX accounts/rates and accounting periods through existing administration.
3. Add actual founders/partners from Founder Overview or Ownership → Shareholders. Link an ERP account only when identity administration is authorized. An external participant has no pretend login or automatic consent.
4. Record company funding, a founder-paid expense or a payment against an existing bill/accrual. Another authorized user reviews its evidence and exact accounting preview. FX differences require explicit confirmation. Sensitive approval policies apply before posting. Reject an incorrect source and record a corrected transaction; do not edit its purchasing expense behind the source.
5. Create and activate an effective sharing policy. Allocate a posted founder cost or a personal-only shared cost. Record partial personal transfers and obtain both parties' authenticated confirmations, or authorized external attestations with party-specific evidence. A company reimbursement that overlaps personal recovery is blocked. Resolve with an actual confirmed return or independently verified liability reassignment plus an explicitly authorized audited resolution.
6. Use Expense Sharing tabs for monthly/12-month forecasts, source selection, annual reserves and contribution progress. Saved forecasts are immutable; refreshing/saving creates another revision. Promises create no cash. Designate verified receipts only once; partial company funding requires explicit available company-cash coverage. Consumption links the actual matching posted payment; releasing a funding allocation never reverses the payment itself.
7. For an unregistered company, record a provisional agreement and effective-dated amendments. For a formal register, configure actual share classes and document the legal/register references. Attach all authorization evidence before collecting consent. The owner/requester cannot give another linked shareholder's consent or approve their own proposal. Independent review and explicit documented confirmation precede register effects. Use the as-of date to inspect historical ownership/capital. A new class or contact alone creates no shares/cash.
8. Company statements are paginated, date/participant filtered and exportable with report-export permission. Each control/currency retains its own running balance. Personal settlements have separate records; GL control reconciliation is independent of both UI summaries and funding plans. Contribution Progress compares fulfilled costs with their saved forecast estimate, showing the actual historical rate/base total and cost/FX variance without changing either record.

New migrations are additive. They retain existing financial data, backfill original recovery links under the migration's exclusive schema transaction, and enable mandatory ownership governance with an attributed system audit event. They never seed founders, default agreements, loans, shares or cash. Evidence remains in the existing private storage volume; no new infrastructure service or scheduler is introduced.

Full verification remains `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`. Focused browser acceptance is `powershell -ExecutionPolicy Bypass -File scripts\e2e.ps1 -TestFile phase5.spec.ts`. Each browser run creates and retains its own `mateerp_e2e_<uuid>` database/files on backend 8101. Never aim fixtures at development. After E2E, rebuild the normal frontend with backend URL 8100 before using `npm run start`; a test build intentionally proxies to 8101. Phase 6 requires a separate owner approval.
