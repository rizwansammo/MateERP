# MateERP

MateERP is NetaMate's enterprise resource planning application. It runs as a single-company installation covering finance, billing, purchasing, accounting, founder finance, operations and documents.

**Status:** Phase 1 (project foundation) is complete. Business modules arrive in Phases 2–7. See [docs/architecture.md](docs/architecture.md#roadmap).

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript 5.9 (strict), Tailwind CSS 4 |
| Backend | Python 3.13, Django 5.2 LTS, Django REST Framework 3.18, drf-spectacular |
| Database | PostgreSQL 18 |
| Dev environment | Docker Compose (isolated `mateerp` project) |
| Tests | pytest + pytest-django, Vitest + Testing Library, Playwright |

## Quick start (Windows, PowerShell)

```powershell
Copy-Item .env.example .env              # then set POSTGRES_PASSWORD and DJANGO_SECRET_KEY
docker compose up -d --build             # PostgreSQL + Django API (migrations run automatically)
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev                              # http://localhost:3100
```

- App: http://localhost:3100
- API health: http://127.0.0.1:8100/api/v1/health/
- API docs (dev only): http://127.0.0.1:8100/api/v1/docs/

Run every check: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

## Documentation
- [Development setup](docs/development.md): environment, commands, troubleshooting
- [Architecture](docs/architecture.md): structure, domain boundaries, financial integrity rules, decisions
- [Design reference](docs/design-reference.md): design tokens and dimensions from the approved prototype
- [Phase 1 summary](docs/phase-01-summary.md)
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
