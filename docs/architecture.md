# MateERP architecture

## Deployment model
**Single company, single tenant, modular monolith.**
- Each customer company gets its own installation, PostgreSQL database and private document storage. Nothing is shared between companies.
- Within a company, departments, branches, projects, locations and cost centres are ordinary data, not tenants.
- Explicitly out of scope: multi-company switching or consolidation, shared-tenant schemas, microservices, and HR or payroll (handled by MateHR).

## Runtime topology

```
Browser ──> Next.js (frontend, :3100) ──/api/*──> Django + DRF (backend, :8100) ──> PostgreSQL (:55432)
```

- The browser only ever talks to the Next.js origin. `next.config.ts` rewrites `/api/*` to Django, so there is no CORS surface and auth cookies stay first-party for Phase 2.
- In production, a reverse proxy terminates TLS in front of both services (Phase 7).

## Backend (`backend/`)

| Path | Responsibility |
|---|---|
| `config/settings/{base,dev,test,prod}.py` | Environment-driven settings. `prod` fails fast on a missing or weak secret key or missing allowed hosts. |
| `config/urls.py`, `config/api_v1.py` | `/api/v1/` (DRF `NamespaceVersioning`), OpenAPI schema and Swagger UI (dev only unless `API_DOCS_ENABLED`). |
| `apps/core/` | Cross-cutting platform code: error envelope (`exceptions.py`), request-id middleware and JSON logging, health service. |
| `apps/accounts/` | Custom `User` model, defined before the first migration. Auth features come in Phase 2. |

### Conventions for domain apps
Each domain gets one Django app under `apps/<domain>/`, created when its phase begins:

```
apps/<domain>/
  models.py        persistence only
  services/        business rules and transactions (the only place state changes)
  selectors.py     read/query helpers
  api/             serializers, views, urls (thin: validate, call a service, serialise)
  tests/
```

- Views and serializers never contain business rules.
- Services own `transaction.atomic()` boundaries; `ATOMIC_REQUESTS` is off on purpose.
- Domains talk to each other through services, never by writing each other's tables.

### API conventions
- Versioned under `/api/v1/`. Each domain contributes a `urls.py` included from `config/api_v1.py`.
- Authentication is required by default (`IsAuthenticated`); public endpoints opt out explicitly. Today only `/api/v1/health/` does.
- Errors always use this envelope:
  `{"error": {"code": "validation_error", "message": "…", "details": {…}, "request_id": "…"}}`
  Unknown `/api/*` routes and unhandled exceptions also return it (unhandled ones are generic and never include internals).
- Every response carries `X-Request-ID`. A well-formed incoming id is reused, so it can be traced through the proxy and the logs.
- Decimals are serialised as strings (`COERCE_DECIMAL_TO_STRING`).

### Logging
JSON lines on stdout (`DJANGO_LOG_FORMAT=json`, the default outside dev) with timestamp, level, logger, message and `request_id`. Request lines record method, path, status and duration. The query string is never logged because it can contain personal or financial data.

## Frontend (`frontend/src/`)

| Path | Responsibility |
|---|---|
| `styles/tokens.css`, `styles/globals.css` | Design tokens (light and dark), Tailwind theme mapping, sharp-corner geometry, keyframes |
| `components/ui/` | Reusable design-system primitives (Button, Input, Badge, Panel, Table, StatGrid, …) |
| `components/brand/` | MateERP wordmark and boot splash (software brand only) |
| `components/shell/` | AppShell, Sidebar, Header, Breadcrumbs |
| `features/<area>/` | Feature UI. Phase 1 has `system/` (health panel, planned-module page). |
| `lib/api/` | Typed API client (`ApiError` from the envelope) and endpoint modules |
| `lib/navigation.ts` | Navigation tree with the delivery phase of each module |
| `lib/preferences.ts` | Theme and sidebar preferences (`data-theme` and `data-sidebar` on `<html>`, set before paint) |

- Presentation stays separate from API access and calculations.
- Monetary values stay strings in the UI. Authoritative calculations happen on the server.

## Domain boundaries (planned)

| Domain app | Phase | Owns |
|---|---|---|
| `accounts`, `administration` | 2 | Users, roles, permissions, approvals, audit log, company profile, branding versions |
| `accounting` | 3 | Chart of accounts, journals and lines, periods and locks, currencies and FX rates, taxes, bank accounts, reconciliation |
| `sales`, `purchasing`, `documents` | 4 | Customers, invoices, payments, receipts, credit notes; vendors, bills, expenses, POs; file storage and metadata |
| `founders`, `ownership` | 5 | Contributions, founder-paid expenses, sharing policies, settlements, loans; shareholders, capital, transfers |
| `inventory`, `assets`, `budgeting`, `catalog`, `reporting` | 6 | Stock, valuation, fixed assets and depreciation, budgets and cost centres, products and services, statements |

### Financial integrity design (Phase 3 foundation)
1. **One posting engine.** Other domains never write ledger rows. They call `accounting.services.post(...)` with a source document reference, and the engine creates a balanced journal. Each journal links back to its source (type and id) and each source records its journal.
2. **Balanced by construction.** Sum of debits = sum of credits per journal, per currency, checked in the service and backed by a database constraint or trigger.
3. **Immutability.** Posted journals are append-only. Corrections are reversal journals that reference the original, or adjustments. No `UPDATE` or `DELETE` on posted lines.
4. **Periods.** Fiscal periods can be locked. Posting into a locked period is rejected by the service.
5. **Idempotency.** Mutating financial endpoints accept an `Idempotency-Key`, and source documents carry unique posting keys, so a retry never double-posts.
6. **Transactions.** Every multi-row financial change runs in `transaction.atomic()`, with row locks (`select_for_update`) where balances are read and updated.
7. **Exact money.** `NUMERIC(20, 4)` amounts, `Decimal` arithmetic and explicit rounding per currency exponent (ROUND_HALF_UP unless policy says otherwise). Never float.
8. **Reconciliation.** Statement lines link to journal lines through explicit match records with user and timestamp.
9. **Founder finance.** Founder-to-founder personal settlements are recorded outside the company ledger. They never create business expenses or clear company liabilities.
10. **Documents.** Issued invoices and receipts snapshot the branding version and content they were issued with. Generated files get stable ids and numbers and live in private storage, served only through authorised endpoints.

## Key decisions
| Decision | Reason |
|---|---|
| Django 5.2 LTS (not 6.1) | Supported until April 2028. Move to 6.2 LTS once it ships. |
| TypeScript 5.9 (not 7.0) | TS 7's native compiler is too new for the Next.js toolchain. Revisit in a later phase. |
| ESLint 9 (not 10) | Plugin ecosystem for `eslint-config-next` is stable on 9. |
| Same-origin API proxy, no CORS | Smaller attack surface; simpler cookie and CSRF auth in Phase 2. |
| Custom `User` model from day one | Swapping `AUTH_USER_MODEL` after the first migration is very costly. |
| Self-hosted fonts and icons | No runtime third-party requests from a financial application. |
| Preferences on `<html>` attributes + CSS variants | Theme and sidebar width render correctly before hydration, with no flash. |
| Django admin not installed | Not needed yet. Add it deliberately (behind auth) if administration needs it. |
| HSTS preload is opt-in | Preload-list submission is effectively irreversible. |
| No Redis or workers yet | Add them only when a phase needs them (e.g. recurring billing or PDF generation in Phase 4). |

## Roadmap
1. **Project foundation:** complete
2. Authentication and administration
3. Core accounting engine
4. Billing, expenses and documents
5. Founder finance and ownership
6. Business operations and reporting
7. Security, final testing and release
