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

See [accounting-contract.md](accounting-contract.md) for posting, approval, period, reconciliation and history rules. Phase 3 does not issue invoices, receipts or tax filings.

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
