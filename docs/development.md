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
| E2E tests | `npx playwright install chromium` (once), then `npm run build; npm run test:e2e` (backend must be running) |
| **Everything** | `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` |
| Stop stack | `docker compose down` (data kept) |

`docker compose down -v` **deletes the MateERP database and file-storage volumes**. Use it only when you really want a clean installation.

## About the end-to-end tests
- The tests run against your local stack and create data through the app: users prefixed `e2e-`, custom roles named `E2E …`, branding versions and audit events. That data is left in place; nothing is deleted.
- **Before each run**, the global setup:
  - resets the `e2e-admin` account with a fresh random password (never written to disk)
  - clears sign-in throttling (in dev, every browser shares the Docker gateway address)
  - resets the branding approval rule and module toggles
- **Company profile:** the tests reuse an existing company profile or create one called "NetaMate".

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
- **Changed `.env` credentials after the first start:** the database volume keeps the original password. Either revert the change or recreate the volume (destroys local data).
