# MateERP

MateERP is NetaMate's enterprise resource planning application. It runs as a single-company installation covering finance, billing, purchasing, accounting, founder finance, operations and documents.

**Status:** Phase 4 implements sales, billing, verified collections, purchasing, expenses, recurrence and private financial documents on the existing accounting engine. See [Phase 4 report](docs/phase-04-summary.md). Founder finance and ownership remain Phase 5; purchase orders and inventory remain Phase 6.

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript 5.9 (strict), Tailwind CSS 4 |
| Backend | Python 3.13, Django 5.2 LTS, Django REST Framework 3.18, drf-spectacular, Pillow, WeasyPrint |
| Database | PostgreSQL 18 |
| Dev environment | Docker Compose (isolated `mateerp` project) |
| Tests | pytest + pytest-django, Vitest + Testing Library, Playwright |

## Quick start (Windows, PowerShell)

```powershell
Copy-Item .env.example .env              # NEW installations only; preserve existing environment files
# Set POSTGRES_PASSWORD, DATABASE_URL and DJANGO_SECRET_KEY before starting.
docker compose up -d --build             # PostgreSQL + Django API (migrations run automatically)
docker compose exec backend python manage.py create_admin   # first administrator (interactive)
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev                              # http://localhost:3100 → sign in
```

There are no default credentials. After signing in, set up the company in **Settings → Company Profile**, then branding in **Settings → Invoice & Receipt Branding**.

For accounting, explicitly set up a chart in **Banking & Accounting → Chart of Accounts**, create a fiscal year in **Accounting Periods**, link bank/cash accounts to their GL accounts, then enter a balanced **Journals → Opening balances** draft. Migrations never seed balances or transactions. [Posting rules and future module contract](docs/accounting-contract.md).

For Phase 4, assign unused, postable AR, AP and customer-credit control accounts, configure revenue/expense defaults in **Sales → Sales & purchases setup**, and publish document branding before issuance. Configure applicable tax mappings and FX rates. Recorders cannot verify their own customer payments. Recurrence runs explicitly from the UI or the documented scheduler command; it is not an automatic background service.

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
- [Phase 3 summary](docs/phase-03-summary.md) · [Accounting contract](docs/accounting-contract.md)
- [Phase 4 summary](docs/phase-04-summary.md) · [Resume checkpoints](docs/phase-04-progress.md)
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
