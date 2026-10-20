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

| Container | Purpose | Host address |
|---|---|---|
| `mateerp-db` | PostgreSQL 18 (volume `mateerp-pgdata`) | `127.0.0.1:55432` |
| `mateerp-backend` | Django dev server (code bind-mounted, auto-reload) | `127.0.0.1:8100` |

Ports bind to localhost only, and the names don't clash with other local Compose projects. Change the host ports in `.env` (`MATEERP_DB_PORT`, `MATEERP_BACKEND_PORT`) if needed. Migrations run automatically when the backend container starts.

## 3. Start the frontend
```powershell
cd frontend
npm ci
npm run dev        # http://localhost:3100
```
Requests to `/api/*` are proxied to `MATEERP_BACKEND_URL` (default `http://127.0.0.1:8100`).

## Everyday commands
| Task | Command |
|---|---|
| Backend tests | `docker compose exec backend pytest` |
| Backend lint / format | `docker compose exec backend ruff check .` · `docker compose exec backend ruff format .` |
| New migrations | `docker compose exec backend python manage.py makemigrations` |
| Apply migrations | `docker compose exec backend python manage.py migrate` |
| Django shell | `docker compose exec backend python manage.py shell` |
| Backend logs | `docker compose logs -f backend` |
| Frontend unit tests | `cd frontend; npm test` |
| Frontend lint / types | `npm run lint` · `npm run typecheck` |
| Production build | `npm run build` |
| E2E tests | `npx playwright install chromium` (once), then `npm run build; npm run test:e2e` (backend must be running) |
| **Everything** | `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` |
| Stop stack | `docker compose down` (data kept) |

`docker compose down -v` **deletes the MateERP database volume**. Use it only when you really want a clean database.

## Editor support (optional)
Python dependencies live in the container, so the editor reports missing imports. For IntelliSense, create a local venv:
```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\pip install -r requirements\dev.txt
```
Then select `backend\.venv` as the interpreter.

## Troubleshooting
- **Port already in use:** change `MATEERP_DB_PORT` / `MATEERP_BACKEND_PORT` in `.env` and update `frontend/.env.local`.
- **"Set POSTGRES_PASSWORD in .env":** you haven't created `.env` yet (step 1).
- **Dashboard says "backend could not be reached":** check `docker compose ps` and `docker compose logs backend`.
- **Changed `.env` credentials after the first start:** the database volume keeps the original password. Either revert the change or recreate the volume (destroys local data).
