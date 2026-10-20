# MateERP

MateERP is NetaMate's enterprise resource planning application. It runs as a single-company installation covering finance, billing, purchasing, accounting, founder finance, operations and documents.

**Status:** Phase 2 (authentication and administration) is complete. The accounting engine is next (Phase 3). See [docs/architecture.md](docs/architecture.md#roadmap).

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript 5.9 (strict), Tailwind CSS 4 |
| Backend | Python 3.13, Django 5.2 LTS, Django REST Framework 3.18, drf-spectacular, Pillow |
| Database | PostgreSQL 18 |
| Dev environment | Docker Compose (isolated `mateerp` project) |
| Tests | pytest + pytest-django, Vitest + Testing Library, Playwright |

## Quick start (Windows, PowerShell)

```powershell
Copy-Item .env.example .env              # then set POSTGRES_PASSWORD, DATABASE_URL and DJANGO_SECRET_KEY
docker compose up -d --build             # PostgreSQL + Django API (migrations run automatically)
docker compose exec backend python manage.py create_admin   # first administrator (interactive)
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev                              # http://localhost:3100 → sign in
```

There are no default credentials. After signing in, set up the company in **Settings → Company Profile**, then branding in **Settings → Invoice & Receipt Branding**.

| What | Where |
|---|---|
| App | http://localhost:3100 |
| API health | http://127.0.0.1:8100/api/v1/health/ |
| API docs (dev only) | http://127.0.0.1:8100/api/v1/docs/ |

Run every check: `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`

## Documentation
- [Development setup](docs/development.md): environment, first administrator, commands, troubleshooting
- [Architecture](docs/architecture.md): structure, security model, domain boundaries, financial integrity rules
- [Design reference](docs/design-reference.md): design tokens, components and document templates from the approved prototype
- [Phase 1 summary](docs/phase-01-summary.md) · [Phase 2 summary](docs/phase-02-summary.md)
- [CLAUDE.md](CLAUDE.md): project conventions for AI-assisted development

## Repository layout

```
backend/         Django project (config/) and domain apps (apps/)
frontend/        Next.js application (src/), unit and e2e tests (tests/)
docs/            Architecture, setup, design reference, phase summaries
scripts/         Windows-friendly helper scripts
.github/         CI workflow
compose.yaml     Local development stack
```
