# Phase 6 — implementation and acceptance report

Status: **Phase 6 implemented and locally verified, 2026-10-22.** Awaiting owner review.
Approved scope and policy: [plan](phase-06-plan.md). Exact resume state and run
history: [checkpoints](phase-06-progress.md). Work remains uncommitted on `main`;
no branch, commit, push, deployment or Phase 7 work is authorized.

## Implemented integration

- Existing catalog identities, stock/nonstock/service profiles, units/categories,
  dated prices, explicit commercial quotations and assumed-cost margin scenarios.
- Frozen purchase orders/revisions and independent approvals, partial receiving,
  service acceptance, private evidence, exact supplier-bill matching, explicit
  acquisition price corrections and source-linked supplier cancellations.
- Company-wide weighted-average stock, location quantities, paired transfers,
  retained counts/cost corrections, chronology/negative-stock guards and GL checks.
- Documented control-transfer contracts, distinct dispatch/control/invoice events,
  unbilled/deferred clearing, frozen COGS and accepted returns separate from credits.
- Real-source asset claims, retained original currency/FX, planned vs posted
  straight-line depreciation, prospective estimates, disposal/actual-sale links and
  unused-capitalization correction/replacement with retained history.
- Cost centers, append-only analytical classifications, independently approved
  immutable budget revisions, original/revised/posted comparisons and journal drilldown.
- Practical historical entry, pre-registration evidence without GL, independent
  adoption, mutually exclusive reconstruction/opening/linking, original/recognition
  date disclosure and private participant-scoped evidence.
- Permission-aware dashboard/report library, historical GL aging, native-currency
  projections, exact cash-flow classifications, meaningful filters/sorting and
  bounded formula-safe exports. Forecasts remain separate from company actuals.

## Main code areas

Backend domains: `apps/catalog`, `apps/inventory`, `apps/assets`, `apps/budgeting`,
`apps/reporting`; procurement extends `apps/purchasing`; fulfillment extends
`apps/billing`; onboarding extends `apps/accounting`. Existing source-owned financial
adapters, files, approvals and audit services remain authoritative.

Frontend: `features/operations/{Catalog,Procurement,Inventory,Fulfillment,Assets,
Budgets,CostClassification,Onboarding,Dashboard,Reports,CashFlow}.tsx`, corresponding
App Router destinations, commercial dated-price controls and existing project
financial integration. Current phase/version are 6 / 0.6.0.

The final visual review also corrected the existing financial text formatter:
fractional unit costs keep their significant digits and currency prefix, including
symbol presentation. This changes presentation only; amounts, inventory movements
and journals are untouched. Posted monetary precision is still validated by the
backend. The new regression covers 650/7 → 92.857143 and values above JS safe integers.

## Verification evidence

The comprehensive local campaign is logged in the ignored
`backend/.cache/phase-06-verification-final.log`. Its first browser portion found
integration failures, which were corrected and rerun. The final complete browser
run is `backend/.cache/phase-06-browser-final-acceptance.log`, exit 0. Results below
are actual local checks, not a claim of a remote GitHub CI run or one uninterrupted
all-green first attempt.

| Check | Actual result |
| --- | --- |
| Full PostgreSQL pytest, including Phases 1–5 | **409 passed, 419.16s** |
| Last readonly inventory summary + existing stock scenarios | **5 passed, 88.31s**, after the full suite |
| All frontend unit/integration tests after display fixes | **154 passed, 56.66s** |
| Final company module metadata / settings target | **18 passed, 29.77s**, after the full backend suite |
| Final budget utilization / operations / chart target | **42 passed, 14.79s**; exact 80% display, no monetary float conversion |
| Django system check / missing migrations | Passed / none missing |
| Ruff lint / format | Passed; final check reports 346 files already formatted |
| OpenAPI | Validation passed with zero warnings |
| ESLint / strict TypeScript | Passed |
| Next.js production build | Passed |
| Complete isolated Playwright | **60 passed, 14.3m**, zero failures/skips; includes one authentication setup and all Phase 1–6 browser regressions |

Earlier targets also passed: affected accounting regression210; source chronology
and approval13; supplier return/count/correction7; independent-connection stock/
asset/depreciation concurrency4; expanded isolated Phase6 browser8. These are
overlapping campaigns, not additional unique test counts. The first full browser
run ended45 passed /3 failed /12 not run: disabled-module routes bypassed the old
notice, a test still expected planned purchase orders, and the interrupted module
toggle left inventory disabled for later setup. Fixed the actual route guard and
explicit Functional metadata, updated obsolete expectations, then reran all60 tests
with a fresh database. Earlier failed attempts are retained in the progress log;
no claim that every attempt passed is made.

Applied additive migrations end at accounting0011, billing0007, inventory0007,
purchasing0012, assets0005, budgeting0002, reporting0002 and files0006. No financial
records or balances are seeded. Development baseline counts checked again:
users59, company1, private files15; accounts/journals/invoices/expenses/vendor bills0.

## Acceptance coverage

| Approved scenarios | Owning verification |
| --- | --- |
| A–C: stable catalog and historical commercial prices | `catalog/tests/test_catalog.py`, legacy billing/invoice regressions, dated-price UI tests |
| D–K: order approval, partial receiving, matching and duplication | `inventory/tests/test_procurement_api.py`, `test_stock.py`, `test_counts.py`, private-file tests |
| L–T: exact WAVG, transfers, counts, chronology and GL | `inventory/tests/test_costing.py`, `test_stock.py`, `test_counts.py`, `test_concurrency.py`, `test_supplier_returns.py` |
| U–X: draft/dispatch/control/invoice/return separation | `inventory/tests/test_fulfillment.py` plus retained Phase4 invoice/credit tests |
| Y–AD: source claims, depreciation, periods and disposal | `assets/tests/test_assets.py`, `test_concurrency.py`, asset UI/browser scenarios |
| AE–AI: approved plans, actuals and classification | `budgeting/tests/test_budgets.py`, exact 10000/8000/2000/80% UI display, independent browser approval |
| AJ–AO: dashboard, aging, provenance and safe exports | `reporting/tests/test_reporting.py`, accounting reports, founder forecast/personal separation regressions |
| AP–AV: permissions, CSRF, immutable sources and UI states | Existing auth/security suites, new restricted APIs, PostgreSQL guard/concurrency tests, full isolated browser campaign and screenshots |
| Mandatory historical/startup clarifications | `accounting/tests/test_onboarding.py`, existing founder/expense tests and historical-entry browser scenario |

All browser scenarios passed in fresh retained database
`mateerp_e2e_225f606546b74e3896630548c778c4af` on backend 8101 through
`localhost:3100`. Its files are isolated under the existing storage volume's
`e2e/<database>` path. The runner stopped only its test backend afterward.

## Representative accounting treatment

These are base-currency examples without tax or FX, not development seed data.
Each journal is posted through the existing central engine with a source/action
identity. Source records, period checks, approvals and exact reconciliation remain
in force; cash and AP are never repeated by an operational action.

| Event | Debit | Credit |
| --- | --- | --- |
| Receive 10 units at 100 and 10 at 200 | Inventory 3000 | GRNI 3000 |
| Match that receipt to its vendor bill | GRNI 3000 | Accounts payable 3000 |
| Transfer five units between company locations | No GL entry | Paired retained quantity legs only |
| Transfer customer control of five units, WAVG 150 | COGS 750 | Inventory 750 |
| Authorized retained-stock impairment of 50 | Adjustment expense 50 | Inventory 50 |
| Capitalize an eligible posted expense acquisition | Fixed assets 60000 | Original acquisition expense 60000 |
| Full straight-line month, 60000 / 60 months, zero residual | Depreciation expense 1000 | Accumulated depreciation 1000 |

Control transfer also recognizes contract revenue once: debit Unbilled / credit
Revenue when control precedes invoicing. The later invoice debits AR and clears
Unbilled. An invoice preceding control credits Deferred revenue, which the control
event debits against Revenue. Dispatch alone has no revenue/COGS journal. The
contract's documented policy selects this treatment; dates alone never do so.

For a sale of an asset costing 60000 with accumulated depreciation 40000 and
actual invoiced proceeds 25000: the existing invoice first posts AR 25000 / sales
revenue 25000. Disposal then debits accumulated depreciation 40000 and that invoice
revenue 25000, credits fixed assets 60000 and disposal gain 5000. Net carrying value
removed is 20000 and the gain is 5000. Collection remains a separate verified
payment. Retirement/write-off has no invented proceeds or receivable.

The WAVG, original-return cost, remaining-pool value, receipt/GRNI matching,
acquisition claims and budget actuals are independently tested against source
records and GL. Existing AR/AP, founder controls, bank carrying values and immutable
PDF/security tests are included in the retained full backend regression suite.

## Dashboard and report inventory

Dashboard recognized income/expense/profit and monthly series read posted GL.
Cash receipts/payments exclude internal transfers and opening/cutover; cash-flow
classification separately discloses FX and unclassified activity. AR/AP aging uses
dated allocations. Stock and asset values use source reconciliation; budget
utilization uses approved scopes and posted actuals. Pending documents are labelled
current workflow counts and are not historical revenue. Date ranges use company
time zone, with equal-length prior comparisons. Restricted users do not receive
company financial metrics. Personal settlements and forecasts remain separate.

The permission-filtered library has 38 stable destinations, including existing
source views rather than duplicate report engines:

| Category | Completed views |
| --- | --- |
| Financial | Profit & Loss; Balance Sheet; Cash Flow; Trial Balance; General Ledger; Income by Account; Expenses by Account; Tax Summary; Receivables Aging; Payables Aging; Bank Transaction Summary; Historical Onboarding Provenance |
| Sales | Invoicing by Customer; Invoicing by Product / Service; Invoicing & Collection Trends; Project Financial Performance; Recurring Revenue Analysis; Sales Order Performance; Credits & Refunds |
| Founder | Founder Contributions; Founder-Paid Expenses; Shared Expenses; Personal Settlements; Founder Loans; Company Reimbursements; Funding Plan Summaries |
| Operational | Inventory Valuation; Stock Movements; Stock by Location; Low Stock; Purchase Order History; Goods Receipt History; Vendor / Purchase Analysis; Fixed Asset Summary; Posted Depreciation; Asset Disposals; Budget Variance; Cost Center Performance |

New filter-preserving CSV projections cover income, expense, AR/AP aging,
customer/product invoicing, vendors, locations, low stock, receiving, historical
provenance, recurring contracts, bank activity and taxes. Existing GL/statements,
cash flow and founder statement exports remain available in their owning views.
The library's source-workflow links do not imply an additional CSV export on every
directory. CSV authorization requires `reports.export`, safe cells include headers,
exact decimals are preserved, and oversized projections fail explicitly at the
10000-row bound. Recurring run rate is labelled contractual, not recognized income.

## Security and historical safeguards

New operations use current database permissions, CSRF, source-scoped authorities,
company-first locking, atomic writes, frozen approvals and append-only evidence.
Independent reviewers cannot approve their own protected actions. Private file
metadata and actual bytes share purpose/reference and participant restrictions.
Disabled-module routes wait for configuration before mounting working controls;
backend checks remain authoritative. Existing module history is retained.

Historical evidence starts without GL. An independently reviewed disposition
chooses reconstruction, opening-only cutover or linking an already verified source.
These choices are mutually exclusive for the retained original identity. Startup
evidence is not corporate adoption, a loan or share issuance. Original and permitted
recognition dates, historical currencies/rates, funding source and audit references
remain visible. Personal founder settlement never automatically reduces company
liability. Existing overlap-recovery protection continues to apply.

## Explicit operating boundaries

Valuation is company-wide; location quantities do not create financial ledgers.
Unsupported retroactive recosting and negative stock are rejected. Bill matching
uses exact historical consideration; supplier changes require explicit review.
Supplier cancellation currently requires unmatched goods. Existing posted/settled
bill consideration must use its owning correction/payment/reconciliation workflow
first; this phase does not create an unrestricted vendor-credit/refund engine.

Customer returns use frozen original fulfillment cost. A later separately reviewed
acquisition variance is never silently used to rewrite that historical issue;
subsequent cost reallocation uses a documented source-linked valuation correction.
Depreciation is straight-line, with explicit service-month posting. Unused
capitalization reversal is limited to assets without posted depreciation/disposal;
consumed assets use the documented disposal/current-period correction path.

Cash movements without sufficient economic evidence remain unclassified. Cash
classification is not statutory certification. Exports are bounded CSV; report PDFs,
automatic background jobs, payroll and unrelated infrastructure are not introduced.
Historical provenance/independent review cannot infer semantic duplicates with
invented new references; operators must retain original evidence and correct sources.

## Start locally

Use the existing Windows setup in [development](development.md):
`docker compose up -d backend`, apply additive migrations, then `cd frontend` and
`npm run dev` (3100 → backend8100). Browser tests use fresh isolated databases on8101
via `scripts/e2e.ps1`, never the normal development installation. Rebuild for8100
after a browser-test production build before using `npm run start`.

## UI fidelity review

Final light/dark/compact/off-canvas inventory captures were inspected beside the
read-only prototype capture at 1440×900. Sidebar widths are 264/64px, header 56px,
main content starts at x292 when expanded, cyan is #00B0F0, light sidebar #0A0F16,
and IBM Plex/Astro branding, sharp geometry and established surface tokens remain.
The KPI strip, cyan value chart, dense table and panel spacing follow the reference.
The fractional cost now correctly reads 92.857143 in both themes.

The production capture has no reorder warning because its actual seven units are
above the configured zero threshold; the reference sample has a warning. That
accounts for the vertical banner difference. Production tables/actions expose real
source-owned workflows, search/pagination and GL reconciliation rather than the
prototype's simulated controls. Universal pixel identity is not claimed. Existing
390px mobile regression and the new 820px off-canvas/escape behavior passed.
Final captures are retained in ignored `backend/.cache/phase-06-visual/` and
`frontend/test-results/`. The temporary reference preview was stopped after capture;
the prototype working tree remains clean.

## Final acceptance

Milestones **6A, 6B, 6C and 6D are complete** for owner acceptance. Financial
adapters remain source-owned; no second ledger, bank cache or background service
was added. No Phase 7 implementation, deployment or remote Git operation occurred.

Branch is `main`; HEAD remains
`aec67d23203f14eaa25642a4dd405be1d876bdb8`. All Phase 6 changes remain unstaged and
uncommitted. The expected origin is `https://github.com/rizwansammo/MateERP.git`.
Both original volumes, `mateerp-pgdata` and `mateerp-storage`, remain present.
Normal backend/database use loopback 8100/55432; the isolated test backend is stopped.
The normal frontend was rebuilt for8100 and restored on3100. Same-origin health
and Login returned200, with version0.6.0/databaseOK; anonymous dashboard/inventory
requests returned307 toLogin. Final ESLint and production build/type checks passed.
Development counts remain 59 users, one company and 15 private files, with zero
accounts, journals, invoices, bills, expenses, historical records, stock events,
asset registrations or budgets. No browser fixtures were run against development.

Phase 7 is ready for a separate owner-approved release-hardening effort: production
configuration/security review, backup-and-restore rehearsal, realistic-volume
performance, deployment/runbook validation and final release acceptance. These
activities are not represented as completed by Phase 6's local test results.

Suggested commit message (owner commits/pushes):

```text
feat: complete Phase 6 operations, historical onboarding and financial reporting
```
