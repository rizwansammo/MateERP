# Phase 5 — approved implementation plan

Approved by the owner on 2026-10-21, including the four policy defaults and three mandatory clarifications below. Base: `main`, `eb9abb22ec67e7224453f5d202eecfccc933bf54`. No branches, commits, pushes or deployments are authorized.

## Boundaries and architecture

Extend the existing modular monolith with `founders` and `ownership`. Corporate accounting, personal settlements and funding forecasts are separate systems of record with explicit references. Only corporate events use the existing accounting posting service and scoped domain authority. No second ledger, bank balance cache, recurring-expense engine or company identity is introduced.

Shared financial-party identity belongs to `company`; founder and shareholder participation reference it. Support people, organizations, external shareholders, optional ERP accounts and any number of founders. Never seed real founders or financial history automatically.

Models cover funding receipts, loans, founder-funded purchasing sources, corporate obligations and settlement allocations; versioned sharing policies and immutable personal allocations/confirmations; versioned forecasts, requests/pledges, verified funding designations and reserve cycles; provisional ownership agreements/amendments, formal share classes/proposals/event lines, consents, evidence and historical snapshots. New private evidence uses existing validated storage and purpose/reference policies.

## Mandatory owner clarifications

1. **Provisional ownership:** support effective-dated amendments, including agreed 50:50 becoming 40:40:20. Preserve earlier agreements and approvals. These are agreement amendments, never formal share transfers or issuances. Formal registration is a distinct documented setup.
2. **Shareholder authorization:** every affected transferor must authorize their proposed transfer, independently of governance approval. Linked users consent as themselves; an authorized operator may record an evidence-backed attestation for a shareholder without an account, explicitly attributed to the operator. Never impersonate. Freeze proposal/evidence identity, reject stale consent and revalidate before confirmation.
3. **Double recovery:** detect overlap between corporate founder obligations and confirmed personal expense-sharing settlements. Block reimbursement if it would duplicate recovery until an explicitly authorized, audited resolution is recorded. A personal settlement never automatically reduces a company GL liability. Resolutions require actual confirmed returns or a separately approved corporate reassignment/reclassification, with exact source allocations.

## Accounting treatment

| Event | Debit | Credit |
|---|---|---|
| Verified loan receipt | Company bank | Founder loan liability |
| Verified other-equity funding | Company bank | Configured contributed equity |
| Unclassified actual receipt | Company bank | Pending-funding liability |
| Qualified paid-in share capital | Bank or previously posted pending funding | Share capital and applicable premium |
| New founder-paid business expense | Existing purchasing expense/input-tax calculation | Founder payable, loan or authorized equity |
| Founder settles posted vendor bill/accrual | Historical AP | Founder obligation/equity, with disclosed FX if necessary |
| Reimbursement / principal repayment | Historical founder payable / loan | Company bank at carrying value |
| Approved liability reassignment | Original founder liability | New founder liability |
| Personal transfer / pledge / forecast / reserve target | No GL entry | No GL entry |

Each receipt has one exclusive classification. No cash is recorded twice when pending funding is classified or subscriptions are matched. Existing bills are settled without repeating expense. Exact partial allocations consume the original base carrying value and the final allocation clears its exact remainder. Reversals preserve links and downstream constraints.

Independent source-to-GL reconciliation covers founder payables, loans, pending funding and recognized equity. Configure unused, correctly typed control accounts explicitly; never relabel used history or invent opening balances. Existing-history setup requires evidence and reviewed reclassification/allocation.

## Approved defaults

- Unpaid subscriptions are disclosed commitments; no automatic cash or subscription receivable. Explicit account mappings and documented confirmed issuance are required for share-capital classification.
- Loans support principal and recorded terms; no automatic interest accrual.
- Governance uses configurable distinct approval counts, initially one independent approver. No self-approval for sensitive ownership actions. Existing approval categories retain their prior one-decision behavior.
- Participants without accounts use authorized, evidence-backed attestations attributed to the operator, never simulated authenticated confirmations.

## Sharing and personal settlements

Version equal, custom and explicitly provisional/formal ownership-based policies with effective dates and default/category precedence. Prevent ambiguous intervals and allocations outside participation dates. Freeze weights, ownership source and amounts per approved expense allocation. Use Decimal/integer minor units and deterministic largest remainder (stable participant ID ties), including exact equal thirds. New policies never rewrite earlier allocations.

Record settlement parties, source allocations, currency/date/reference, evidence, recorder, confirmations and disputes. Partial confirmations cannot over-settle. Sharing obligations and transfers are non-GL. Corporate and personal statements remain visibly separate. Reimbursement review enforces the mandatory overlap block described above.

## Monthly planner and annual reserves

Reuse Phase 4 schedule/date generation and tax calculations. Give each occurrence one identity; generated drafts/posted expenses replace, rather than duplicate, forecast occurrences. Account for paused/cancelled schedules, existing actual payments and explicitly selected one-off obligations. Plans do not generate expenses automatically.

Save immutable forecast revisions containing source configuration, policy/ownership weights, native amounts, estimated FX source/rate and estimates/completeness. Refresh creates a new revision. Actual postings retain their own historical FX and show variance. Distinguish expected, requested, pledged, recorded, verified, allocated and remaining funding. Support founder-funded, partially company-funded and self-sustaining modes using explicit funding coverage.

Required examples: monthly VPS 4,000 + subscription 2,000 = BDT 6,000; December annual renewal 1,200 gives 7,200. 50:50 means 3,000 each normally and 3,600 in December; 40:40:20 means 2,400/2,400/1,200 and 2,880/2,880/1,440.

Reserve cycles reference a specific renewal, target/start/due date and policy snapshot. A 1,200 annual target over twelve months is 100/month, or 50 each at 50:50. Planned accumulation is separate from verified designated funds; designations cannot consume the same receipt twice. Verify current GL cash coverage, disclose shortfalls and consume retained funds once. In the renewal month, the remaining renewal collection includes that month's installment. With 1,100 actually accumulated, collect 100; with none accumulated, collect 1,200, never 1,300. Preserve price/date/policy changes, early renewal, surplus and shortfall history.

## Ownership and capital

Provisional percentage agreements are immutable effective-dated versions; amendments require participant authorization and governance review. Formal percentages derive from confirmed share units. No implicit conversion of agreements to shares. Support configured classes; do not present unlike voting/economic rights as equivalent.

Formal transfer groups are atomic. At 10,000 total units, 1,000 transferred by each of two 5,000-unit holders produces 4,000/4,000/2,000. Ten percentage points is distinct from 10% of a holder's units. Reject inexpressible fractional-unit targets. Independent issuance of 2,500 creates 12,500 total and 40:40:20 dilution. Private consideration is not company revenue or cash.

Freeze proposals, consents, required votes and document references. Reserve pending transfer availability, prevent concurrent overselling, and recheck the entire affected effective-date sequence at confirmation. Approved proposals alone do not alter holdings. Require legal/reference evidence for formal confirmation. Preserve recorded historical snapshots; corrections are append-only and cannot invalidate later confirmed holdings. Clearly distinguish proposed, approved, legally documented/confirmed, future-effective and rejected changes.

Reconcile issued units/nominal value, paid-in share capital, premium, other equity and unpaid commitments separately. No government filing or legal registration is claimed.

## APIs, permissions and integration

Use `/api/v1/founders/` and `/api/v1/ownership/`, thin typed serializers/views, domain services, existing error/pagination/OpenAPI conventions and the same-origin session/CSRF proxy. Previews are server-calculated. No request can manufacture posting authority or trusted balances.

Retain existing codes and add narrow verification, liability, personal sharing/confirmation, planning, ownership view/approval/attestation permissions. No automatic new sensitive grants to existing non-admin roles. Review default Finance Manager grants deliberately. Enforce participant/object scope, module settings and private evidence access for metadata and bytes. Mask sensitive source metadata in general reports when appropriate without changing GL totals.

Extend approvals with immutable unique actor votes and frozen requirements; execute once at quorum. Preserve existing categories and regression tests. Ownership approval does not replace transferor consent. Recheck current permissions and requester eligibility before execution. Audit all sensitive actions without credentials.

Extend existing purchasing expense funding and source-linked AP settlement; reuse exact tax/debit logic, recurrence, treasury FX/quotes, period/reconciliation guards, document viewer, private storage and audit. Source/number/journal/allocation changes are atomic with the company financial lock first. Canonical fingerprints and source identities prevent replay conflicts and duplicate posting. Add DB constraints/triggers and separate-connection race tests.

## UI

Reimplement prototype Founder/Ownership layouts using production primitives. Founder routes: overview, contributions, expenses, sharing, settlements, loans, reimbursements, statements. Ownership: shareholders, overview, capital, transfers, issuance, history. Founder profile access is integrated with these screens, not a new global menu. Sharing tabs contain policies, monthly planner, 12-month forecast, reserves, contribution progress and allocations.

Preserve 264/64px sidebar, 56px header, #0A0F16/#00B0F0, IBM Plex/Astro, sharp corners, 24/28/56 page padding, 1640px maximum width, 18px gaps, KPI strips, dense tables, document/accounting panels, approval status and established drawers. Real APIs only; loading/error/empty/denied/dirty-state behavior and safe retry keys. Enable Phase 5 navigation only for working destinations; Phase 6 stays planned.

## Seven implementation stages

1. Foundation/governance: identities, account purposes, permissions, approval votes, schema and private evidence.
2. Corporate finance: receipts/classification, loans, purchasing integration, liabilities, reimbursements/repayments and reconciliation.
3. Personal sharing: policy versions, approved allocations, confirmations, disputes and blocked duplicate recovery/resolutions.
4. Planner/reserves: recurrence integration, immutable forecasts, exact targets, actual funding links and renewal cycles.
5. Ownership: provisional amendments, formal register, consent, atomic transfers, issuance, historical/capital reconciliation.
6. Frontend/integration: all routes/forms/previews/approvals/files, module/permission navigation and prototype comparison.
7. Verification/documentation: financial/direct-DB/concurrency tests, full regressions, isolated browser acceptance and final report.

## Verification and delivery

Map prompt scenarios A–AE plus provisional amendments, shareholder consent/attestation and reimbursement blocking to real PostgreSQL tests, Vitest and Playwright. Test exact splits, annual timing/reserve nonduplication, FX estimate/actual separation, immutability, permission changes, file metadata/bytes, period locks and races. Browser fixtures only use `scripts/e2e.ps1` isolated per-run databases/backend 8101. Never seed development finance or delete databases/volumes.

Run Django checks, applied migrations/drift, Ruff lint/format, full PostgreSQL pytest, OpenAPI fail-on-warning, ESLint, strict TypeScript, Vitest, production build, full isolated Playwright regression and Git whitespace checks. Inspect light/dark/compact/mobile views against the read-only prototype. Record only results actually run; no claim of remote CI success.

Maintain `phase-05-progress.md`; produce `phase-05-summary.md` and update architecture/accounting/development/design/README and both agent files. Preserve development data and existing Docker volumes. Final report includes features, journal examples, planner/ownership demonstrations, integrity/security, exact test results, limitations, Phase 6 integration readiness, Git/Docker status and suggested commit message. Stop after Phase 5.
