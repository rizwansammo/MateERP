# Phase 1: Project Foundation (summary)

**Status:** complete, pending user review · **Date:** 2026-10-20 · **Branch:** `main` (uncommitted; the user commits)

## Delivered
**Backend (`backend/`)**
- Django 5.2 LTS + DRF 3.18 project with `base` / `dev` / `test` / `prod` settings, all configured from environment variables. `prod` fails fast on a missing or weak secret key or missing allowed hosts, and enforces HSTS, secure cookies, SSL redirect, `X-Frame-Options: DENY` and nosniff.
- PostgreSQL 18 via psycopg 3 with connection health checks.
- Initial migrations, including a custom `accounts.User` model so auth can be extended safely in Phase 2.
- `/api/v1/` namespace versioning. `GET /api/v1/health/` returns status, service, version, environment, server time and DB status with latency, or 503 when the DB is down. It exposes no configuration.
- Standard error envelope for DRF errors, unknown API routes and unhandled exceptions. Authentication is required by default. Decimals serialise as strings.
- Request-ID middleware and JSON structured logging (paths only, never query strings).
- OpenAPI schema and Swagger UI at `/api/v1/schema/` and `/api/v1/docs/` (dev only by default).
- Multi-stage Dockerfile: dev runs runserver, prod runs gunicorn as a non-root user.

**Frontend (`frontend/`)**
- Next.js 16 + React 19 + strict TypeScript + Tailwind 4, built from scratch with no starter template and no prototype code.
- Design system: light and dark tokens taken from the prototype, an empty radius scale (sharp corners), self-hosted IBM Plex, Material Symbols Sharp and the Astro wordmark font.
- Components: Button, IconButton, Icon, Input, AmountInput, Select, Textarea, Field, Badge, Panel, PageHeader, Table primitives, StatGrid, EmptyState, Spinner.
- Application shell matching the prototype:
  - MateERP wordmark and compact mark, branded boot splash
  - 264/64px sidebar with groups, active states and sub-menus
  - 56px header with breadcrumbs
  - Light and dark theme switching; sidebar collapse with no flash on load
  - Off-canvas navigation below 1000px
- Same-origin `/api` proxy to Django and a typed API client that parses the error envelope.
- Dashboard shows live backend and database health. Every other module shows an honest "Planned · Phase N" page. Header features not built yet (search, New, notifications, account) are disabled and say so.
- Internal `/design-system` reference page (not in the navigation).

**Infrastructure and docs**
- `compose.yaml`: isolated `mateerp` project (`mateerp-db`, `mateerp-backend`, volume `mateerp-pgdata`), loopback-only ports 55432 and 8100.
- `.env.example` files; `.env` is gitignored.
- `scripts/verify.ps1` runs every check. `.github/workflows/ci.yml` runs backend and frontend checks on push to `main`.
- README, CLAUDE.md, architecture, development setup, design reference and this summary.

## Verification results (2026-10-20, local Windows + Docker Desktop)
| Check | Result |
|---|---|
| Django system check | pass |
| `makemigrations --check` | no missing migrations |
| ruff lint + format | pass |
| pytest (real PostgreSQL 18) | **19 passed** (config, DB connectivity, migrations, prod deploy checks and fail-fast, health 200/503, no config leakage, error envelopes, auth-by-default, decimals, request IDs) |
| ESLint | pass |
| TypeScript `tsc --noEmit` | pass |
| Vitest | **35 passed** (navigation, breadcrumbs, API client, health panel, theme, sidebar, UI components, wordmark) |
| `next build` | pass (dashboard, design system and 74 module routes pre-rendered) |
| Playwright e2e vs live backend | **10 passed** (redirect, tokens, collapse 264↔64 with persistence, theme persistence, planned modules, 404, mobile drawer, API proxy, error envelope through proxy, live health) |
| Visual comparison vs prototype | sidebar width/colour, header height, backgrounds and active-item geometry identical in light, dark and compact modes |

## Known limitations
- Company identity (sidebar card, breadcrumb root) shows "Company not configured" until the Phase 2 company profile exists.
- No authentication yet; the only public endpoint is health.
- CI runs lint, types, unit tests and build. Browser e2e runs locally only; adding it to CI needs a backend service in the workflow.
- The prod Docker image does not collect or serve static assets yet; production serving is set up in Phase 7.
- Python packages are only inside the container. For editor IntelliSense, create the optional local venv described in `development.md`.

## Ready for Phase 2
The foundation is ready for Phase 2. It can build directly on:
- the custom User model
- session authentication with CSRF through the same-origin proxy
- the error envelope
- secure-by-default permissions
- the reserved `settings` navigation entries
