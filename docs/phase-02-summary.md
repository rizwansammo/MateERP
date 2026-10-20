# Phase 2: Authentication, Company Settings & Administration (summary)

**Status:** complete, pending user review · **Date:** 2026-10-20 · **Branch:** `main` (uncommitted; the user commits) · **Version:** 0.2.0

## Delivered

**Authentication and security**
- Session sign-in by username or email with show/hide password and "keep me signed in" (14 days; otherwise a browser session with a 12-hour sliding idle timeout).
- Logout flushes the server session. Sessions rotate at sign-in. A password change keeps the current session and ends all others.
- CSRF is enforced on every unsafe request, including anonymous sign-in, and verified through the real browser → Next.js proxy → Django path.
- Protected routing: the proxy redirects requests without a session cookie; the shell layout validates the session server-side; `?next=` is sanitised against open redirects; expired sessions return to sign-in with a notice.
- Sign-in abuse protection: identifier+IP backoff, identifier-wide spacing (never a hard lock) and an IP-wide block. Generic errors; no account enumeration; trusted-proxy-only `X-Forwarded-For`; recovery via expiry, `clear_login_locks` or an admin password reset.
- First-administrator bootstrap: `manage.py create_admin`, with no default credentials.

**Administration**
- **Users & roles:** search, filters, sorting, server pagination, detail drawer, create and edit, activate and deactivate, one-time temporary passwords with a forced change at first sign-in, and password reset.
- **Roles and permissions:** 5 default roles plus custom roles; 23 stable permission codes in 4 categories; a permission matrix with staged changes and an atomic save.
- **Server-side enforcement:**
  - live permission evaluation on every request
  - anti-escalation: you can only grant or assign access you hold, and cannot change your own role
  - the last active administrator is protected
  - the Administrator role is locked
- **Company profile:** an enforced singleton supporting unregistered businesses. Identity, address, contact, tax and registration, base currency, time zone, fiscal year and notes. Edit drawer with unsaved-changes protection; logo management. The sidebar company card shows the live company.
- **Private file storage:** content-validated, re-encoded PNG/JPEG/WEBP on the `mateerp-storage` volume. Purpose- and reference-based object authorisation; signatures and seals are restricted to branding managers.
- **Invoice & receipt branding:**
  - prototype-faithful templates: invoices Meridian, Ledger and Atlas; receipts Official and Compact
  - an SVG stamp-style seal editor or an uploaded seal
  - signature image or typed signature
  - colours, layout, typography, spacing, table style, logo size, footer, terms, payment instructions and custom fields
  - a full-screen branding studio with a live, zoomable preview on fictional sample data
  - Save draft → Publish workflow with immutable, numbered versions (DB trigger), restore-as-new-version, and a read-only version viewer
- **Approvals:** one simple rule per category. *Sensitive administrative changes* (branding publication) is enforced now: publication waits for a designated approver, self-approval is off by default, rejection needs a reason, and the requester can withdraw. Other categories are stored and labelled with the phase that enforces them.
- **Business settings:** financial defaults; currency (enabled currencies, symbol or code, lakh or international grouping); tax configuration (stored only); document number formats with validation and prefix-collision checks.
- **Optional modules:** server-side toggles. Disabled modules are hidden from navigation and their routes say so. Core modules are mandatory. Unbuilt modules stay "Planned".
- **Audit log:**
  - append-only at the DB level, with secrets redacted
  - covers sign-in, user, role, permission, company, logo, settings, module, branding and approval events
  - server-side filters for category, outcome, date range and text, with pagination and a detail drawer showing redacted before → after values
- **Account and personal settings:**
  - Account menu: profile, change password, preferences, about, sign out.
  - Notifications show real pending approvals.
  - Personal preferences (theme, sidebar, rows per page, landing page) are saved to the account without breaking flash-free first paint.

## Verification results (2026-10-20, Windows + Docker Desktop, `scripts\verify.ps1`)

| Check | Result |
|---|---|
| Django system check · `makemigrations --check` | pass · no missing migrations |
| ruff lint + format | pass |
| pytest (real PostgreSQL 18) | **121 passed**: auth, CSRF, sessions, throttle, bootstrap, users, roles, anti-escalation, last admin, company singleton, uploads, file access, business settings, modules, branding versions and immutability, approvals, audit, Phase 1 regression |
| OpenAPI schema | valid, **0 warnings** |
| ESLint · TypeScript | pass · pass |
| Vitest | **80 passed**: login, route guard, open-redirect, session expiry, CSRF client, account menu, sidebar, permission matrix, company drawer, modules, audit filters, users, documents, money, number formats, Phase 1 regression |
| `next build` | pass |
| Playwright vs live stack | **22 passed**: scenarios A–K (bootstrap, session/CSRF, user creation, role enforcement, deactivation, company, branding, modules, approvals, audit, design) plus 10 Phase 1 shell tests |
| Visual comparison | Prototype invoice and receipt templates, settings pages and shell compared side by side and adjusted (currency symbol and lakh grouping on documents, compact 26px row actions) |

## Known limitations and notes
- **Local data from testing:**
  - The dev database now contains a company profile "NetaMate" and branding versions created during browser testing (some use 8×8 sample images).
  - It also holds test accounts prefixed `e2e-`: active administrators named `e2e-boot-…` and `e2e-admin`, plus other `e2e-…` users and `E2E …` roles.
  - Nothing was deleted (no destructive operations). Update the company profile and branding with real details, and deactivate the `e2e-` accounts from Users & roles if you don't want them in this local install.
- **Client IP in development:** the Next.js dev proxy does not forward the browser's address, so every local browser appears as the Docker gateway and shares one IP throttle bucket. In production, place a reverse proxy in front and list it in `MATEERP_TRUSTED_PROXIES`.
- **No email delivery:** temporary passwords are shown once to the administrator for secure manual sharing.
- **Planned (labelled in the UI):** Notification preferences (Phase 4), Integration settings (Phase 7), global search and quick-create (Phases 3–4), and enforcement of non-administrative approval categories by their modules.
- **Branding scope:** previews use sample data only. Issuing documents and PDF generation arrive in Phase 4; issued documents must store their `BrandingVersion`.
- **Phase 3 obligation:** implement `company.services.financial_history_exists()` so base currency and fiscal year lock once journals exist.
- **CI scope:** CI runs backend tests, lint, types, unit tests, build and OpenAPI validation. Browser end-to-end tests run locally against the Docker stack.

## Ready for Phase 3
The accounting engine can rely on:
- permission codes `finance.view` and `accounting.manage`
- the approval executor registry (financial adjustments)
- the append-only trigger function
- the audit service
- company base currency and fiscal settings, with the history guard to implement
- business number formats (journals)
- the error, pagination and transaction conventions
