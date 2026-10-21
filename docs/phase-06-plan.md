# Phase 6 — approved implementation plan

Owner approval includes Milestones 6A–6D and the accounting defaults below. The
three subsequent clarifications are mandatory acceptance requirements. No further
milestone approval is required. Phase 7 is excluded.

## Baseline and preservation

Start: `main`, `aec67d23203f14eaa25642a4dd405be1d876bdb8`, clean working tree.
Phases 1–5 remain authoritative. No branches, commits, pushes, deployment, resets,
database replacement or volume removal. Only Compose project `mateerp` is used.
The PostgreSQL and private-storage volumes are preserved. Existing dependencies,
Windows-native frontend and Docker backend arrangement are retained.

## Implementation sequence

| Milestone | Deliverables |
| --- | --- |
| 6A | Product/service profiles linked to existing BillingItem identities, categories, units and effective-dated prices; purchase orders, frozen approvals/revisions, goods receipts/service acceptance, bill matching and evidence; historical-entry/cutover foundation. |
| 6B | Warehouses, immutable quantity/cost movements, moving weighted-average valuation, transfers, counts/openings, source-owned fulfillment/control transfer/returns and GL reconciliation. |
| 6C | Source-linked assets, capitalization, straight-line depreciation and disposal; cost centers, approved budget revisions and posted actuals; historical onboarding UI integration. |
| 6D | Permission-aware executive dashboard, report library, source drilldown and bounded safe exports; operational UI and integration acceptance; final regression campaign and documentation. |

New domains: catalog, inventory, assets, budgeting and reporting. Procurement
extends purchasing. Existing sales/billing own commercial recognition; accounting
remains the single ledger. Views stay thin, business workflows use services and
atomic transactions with the company financial lock acquired first. New protected
account purposes and permissions are additive. Existing non-admin grants are not
silently expanded. Existing catalog IDs and issued snapshots remain stable.

## Accounting defaults

- Inventory uses a company-wide weighted-average cost pool per tracked item and
  location quantities. Six-decimal quantities; final depletion removes the exact
  remaining value. Transfers do not change company value. No negative stock or
  unsupported retroactive recosting; corrections are traceable permitted-period
  events. Same-day ordering follows serialized posting order.
- Accepted valued goods debit inventory and credit goods-received-not-invoiced
  (GRNI). Matched vendor bills clear the matching GRNI, recoverable tax and
  explicitly reviewed differences to AP exactly once. Purchase order approval has
  no accounting effect. Service acceptance has no warehouse quantity. Matching
  defaults to exact quantities/prices; exceptions need explicit authority and
  retained evidence. Supplier returns retain original acquisition provenance.
- Physical dispatch alone is not revenue recognition. An explicitly documented
  transfer-of-control event is the recognition trigger for configured stock
  contracts. Dispatch, control transfer, invoice, AR, revenue and inventory/COGS
  remain separately identifiable. Unbilled/deferred clearing is used only when the
  documented economic treatment calls for it, never merely because dates differ.
  Legacy Phase 4 invoice behavior is preserved. Each revenue and COGS component
  has one source identity, preventing duplicate recognition.
- Customer returns reference original fulfillment costs and remaining returnable
  quantities. A credit note alone never restocks inventory.
- Asset capitalization claims a real acquisition once, without repeating cash,
  AP or expenses. Depreciation is straight-line from available-for-use, partial
  months prorated, final residual exact, immutable posted months, prospective
  estimate changes. Disposal proceeds and actual collections remain separate and
  use existing billing/payment verification where applicable.
- Budgets are approved immutable revisions. Actuals derive from posted GL,
  separating operating costs, COGS, capital expenditure and recoverable taxes.
  Warnings do not silently block payment. Historical analytical classifications
  use append-only overlays rather than editing journals.
- Cash-flow reporting distinguishes operating/investing/financing, eliminates
  internal transfers and reconciles FX. Unreviewed historical/manual sources are
  disclosed as unclassified rather than guessed.

## Mandatory historical onboarding and startup expenditure

1. Existing expense/founder workflows must permit practical one-by-one historical
   entry with original date, description, currency, payment source, evidence and
   funding classification. Original transaction date and permitted recognition
   date are retained and displayed independently when different.
2. Historical reconstruction obeys rates, currency precision, open periods, bank
   chronology, reconciliation and independent authorization. A closed period is
   not bypassed. Historical contributions, loans, reimbursements and personal
   settlements retain their existing distinct source-owned accounting treatment.
3. A controlled reviewed cutover associates opening balances/outstanding claims
   with their evidence. A historical item included in opening balances cannot
   also post as reconstructed activity. Opening-only vs reconstructed provenance
   is disclosed in source details and reports. No automatically invented historical
   cash movements or duplicate opening journals.
4. Pre-registration founder expenditures may be documented without posting or
   creating a corporate liability, legal capital or formally issued shares.
   Subsequent corporate recognition requires explicit documented authorization,
   appropriate independent approval and one linked existing expense/founder
   workflow. Recording evidence alone creates no company obligation.

## Design and security

The read-only MateERP-UI prototype is the visual/workflow specification. New code
reuses production UI primitives and tokens: 264/64px sidebar, #0A0F16 background,
#00B0F0 accent, 56px header, IBM Plex, sharp corners, dense tables and existing
drawers. No prototype application source is copied. All actions use persistent
APIs, server-side permissions and CSRF; private metadata and bytes share access
policy. Disabled optional modules retain history and legitimate corrections.

## Acceptance and verification

- Catalog compatibility and dated prices; PO lifecycle, frozen independent
  approvals, partial/multiple receipts and matching; no GL on PO approval.
- Weighted average example: 10 × 100 + 10 × 200 = 20 / 3000; issue 5 = 750,
  leaving 15 / 2250. Test fractions, final depletion, locations, transfers,
  chronology, concurrent retries, returns and exact GL reconciliation.
- Explicit control-transfer recognition both before and after invoicing, including
  different periods; dispatch alone cannot recognize revenue or duplicate COGS.
- Asset acquisition claims cannot repeat; 60000/60 months = 1000 for a full
  month; partial/final months, closed periods, repeated/concurrent runs and
  disposal with 20000 carrying value / 25000 proceeds = 5000 gain.
- Budget 10000 / actual 8000 = 80% / 2000 remaining; revisions and scope cannot
  duplicate actuals; drafts and recoverable tax excluded appropriately.
- Historical original/recognition date disclosure, closed-period/FX/reconciliation
  safeguards, cutover-vs-reconstruction duplicate rejection, bank/opening claims,
  startup evidence without GL and independently authorized later adoption.
- Authorization denial, module enforcement, private evidence, audit, CSV formula
  safety, decimal precision, idempotency and posted immutability for new sources.
- Targeted PostgreSQL tests during development; broader affected Phase 1–5 tests
  after shared accounting changes. Frontend unit tests, lint, strict TypeScript,
  OpenAPI, migration checks and production build. Real isolated Playwright through
  `scripts/e2e.ps1`, never the development DB. One comprehensive final verification
  campaign via `scripts/verify.ps1`; no remote CI claim without a real run.
- Visual comparison in light/dark, expanded/compact and responsive layouts.

Maintain `docs/phase-06-progress.md` with exact resume state and actual results.
Mark release 0.6.0/CURRENT_PHASE 6 only when the corresponding implementation is
functional. Finish with acceptance evidence, limitations and a suggested commit
message; stop for owner review before Phase 7.
