# Phase 7D — Performance & Reliability Validation

**Project:** MateERP (single-company ERP)  
**Test date:** 2026-10-22, Asia/Dhaka  
**Source:**  `a836163e1df89619d05c7a226f93b769bd0b9c88` plus **uncommitted** Phase 7A–7C changes in `/home/chatgpt/mateerp-phase7a-audit-20261022`.

## Scope and isolation

- All tests used an isolated Docker Compose project named `mateerp7d` with PostgreSQL 18.6 and Django 5.2.18.
- Database is disposable, ephemeral `tmpfs` with no exposed host port; backend test API port was limited to `127.0.0.1:8101`.
- Test database name: `mateerp_e2e_phase7d`; no existing development or production database was touched.
- Backend test service limited to **1.0 vCPU, 960 MiB**, database limited to **0.5 vCPU, 576 MiB**; Playwright browser tests were serial and low priority.
- No shared Docker network or storage used. The 59 unrelated running containers were captured as a reference list and their status was checked during testing.
- Chromium Headless Shell and its missing libraries were placed under the audit user's home directory, not installed into the global system packages.

## Browser and functional acceptance

- Full **60/60** Playwright Chromium end-to-end tests passed in **7.2 minutes** (7 files, 1 worker).
- Covered session authentication, CSRF, roles and permissions, double-entry journals, closed fiscal periods, bank reconciliation, FX, invoices, refunds, vendor bills, recurring billing, founder finance, ownership and approvals, purchases, inventory/valuation, fixed assets/depreciation, budgeting, reports and CSV exports, private documents and UX/navigation.
- Full fresh database migration sequence completed successfully before browser testing.

## Bounded response-time samples (NOT production load/SLO results)

| Endpoint (GET) | Requests | Max concurrency | Successful HTTP | p50 | p95 | Max |
|---|---:|---:|---:|---:|---:|---:|
| Backend `/api/v1/health/` | 80 | 2 | 80 HTTP 200 | 29.3 ms | 102.5 ms | 157.4 ms |
| Frontend `/login` | 80 | 2 | 80 HTTP 200 | 28.6 ms | 49.2 ms | 67.7 ms |
| Authenticated `/api/v1/accounting/ledger/` | 35 | 2 | 35 HTTP 200 | 169.19 ms | 304.37 ms | 399.38 ms |
| Authenticated `/api/v1/accounting/reports/tb/` | 35 | 2 | 35 HTTP 200 | 169.69 ms | 215.0 ms | 256.09 ms |
| Authenticated `/api/v1/reporting/catalog/` | 35 | 2 | 35 HTTP 200 | 91.86 ms | 181.83 ms | 265.0 ms |

Total: **265 measured GETs**, all expected HTTP 200, maximum two concurrent requests. Preliminary benchmark validation initially compared integer HTTP keys with string keys, causing a false error despite all HTTP 200. Script assertion was corrected, and financial-read benchmark rerun successfully.

**Limits:** These are small, synthetic, local, temporary fixture measurements under Django's E2E development runtime, **not** production Gunicorn, not public Internet latency, not a full representative business-volume dataset, not tested under peak concurrent company workflows. Larger-data query profiling and production-equivalent performance gates belong in Phase 7E staging. These figures do not establish a production SLO.

## Failure and restart recovery

- Controlled restart of **only** `mateerp7d-backend-e2e-1`: health returned HTTP 200 after restart — **PASS**.
- Controlled pause of **only** `mateerp7d-database-1`: health request failed (HTTP 000 / timeout) while unavailable — **expected**.
- Unpause of isolated test database: health returned HTTP 200 — **PASS**.
- Database schema migration count was **113 before and 113 after** the disruption — **PASS**.
- No real production resource was paused, restarted or changed. No evidence of financial data loss in this limited recovery drill; comprehensive audit of live financial balances still requires staging acceptance.

## Open readiness limits

- No completed production-equivalent 7E staging validation, rollback rehearsal with actual GHCR images, large-volume dataset load benchmarks, or offsite production backup activation.
- Source changes remain local in a separate audit workspace; GitHub `main` is unchanged and no production deployment is active.

## Reproduction from dedicated audit workspace

Test-only files: `deploy/performance/compose.test.yml`, `deploy/performance/bin/docker`, `frontend/playwright.7d.config.ts`, `deploy/performance/http-smoke-benchmark.py`, `deploy/performance/financial-read-benchmark.py`, `deploy/performance/scoped-recovery-drill.sh`. Always use the dedicated `mateerp7d` Compose project and read the safety guards before running. The isolated project is intentionally removed after acceptance.
