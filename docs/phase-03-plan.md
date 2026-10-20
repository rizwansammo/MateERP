# Phase 3 implementation plan — Core Accounting Engine

Date: 2026-10-20. Status: approved by the user; implemented under this plan. Verification and exact delivery details are recorded in `phase-03-summary.md`.

## Confirmed starting point

- Production checkout: `C:\Users\Rizwan\Desktop\MateERP`, branch `main`, remote `https://github.com/rizwansammo/MateERP.git`.
- HEAD: `2e55e0a7933705f551ab98edf33989f15793f3f3` (Phase 2). The existing untracked root `AGENTS.md` is user work and remains untouched.
- Prototype: local read-only checkout at `C:\Users\Rizwan\Desktop\MateERP-UI`, revision `2a5c888`; working tree clean.
- `mateerp-db` is healthy; `mateerp-backend` is running. Django reports no issues, all existing migrations are applied, and `makemigrations --check --dry-run` reports no changes.
- Re-run during this review: **121 backend tests passed** against PostgreSQL and **80 frontend unit tests passed**. Builds and browser tests will be run during implementation; earlier reports are not a new verification of them.
- Reviewed: repository conventions, both phase summaries, architecture, development/design documentation, current API/client and security conventions, approval services, company settings, audit/storage services, tests and CI. Read the installed Next.js documentation for routing and data fetching.
- Keep current pinned dependencies, session authentication, same-origin proxy, design system and deployment topology. No additional infrastructure service is needed.

## 1. Domain organization and persistence

Add two domain applications:

| Application | Owns |
|---|---|
| `apps/accounting` | Account hierarchy, fiscal years/periods, journal headers/lines, posting identities and numbers, FX rate history, tax-account mappings, posting/approval services and financial report selectors |
| `apps/banking` | Bank/cash account metadata, treasury-operation references, bank statements/lines, reconciliation sessions and match groups |

Banking owns no separate ledger or mutable authoritative balance. Every balance and treasury transaction is backed by posted accounting lines.

Practical model groups:

- `Account`: unique code, name, type, subtype/report group, parent, normal side, active/postable flags, optional currency restriction and protected control-account purpose.
- `FiscalYear`, `AccountingPeriod`: explicit inclusive date ranges, status, closing/reopening actor, time and reason. Monthly periods are generated from the company's fiscal start; no dates are hardcoded.
- `JournalEntry`, `JournalLine`: draft financial content, document/posting dates, source identity, transaction/base currencies, debit/credit amounts, rate snapshots, creator/poster, immutable posted identifiers, and explicit reversal/adjustment links. Preserve account labels and relevant classifications at posting.
- `PostingIdentity`, `JournalSequence`: canonical request fingerprint, unique posting key/source action, resulting journal and serialized number allocation.
- `ExchangeRate`: transaction currency to company base, effective date, precise positive rate, source, actor and immutable revision history. Transactions retain their actual rate and conversion method.
- `TaxCode` and effective-dated mapping/rate revisions: payable/receivable accounts and manual tax-adjustment references. Preserve revisions already used by postings.
- `BankAccount`: bank/cash type, institution, display name, optional private identifier, currency, active status and unique linked postable asset GL account.
- `TreasuryOperation`: operation/source metadata and journal reference, never an independent posted balance.
- `BankStatement`, `StatementLine`, `Reconciliation`, `MatchGroup` and membership records: dates, native-currency signed amounts, balances, explicit matches and completion/reopening evidence.

Use `PROTECT` relationships and deactivation for historical records. No ordinary delete endpoint for financial history. No automatic financial data or balances in migrations. Provide an explicit, idempotent starter-chart setup with a preview; companies can instead create their own accounts and assign control accounts.

## 2. Shared posting contract and lifecycle

Implement one service entry point, conceptually:

```python
post_journal(
    *, actor, posting_key, source_type, source_id, source_action,
    posting_date, description, lines, journal_date=None,
    draft_id=None, reversal_of=None, adjustment_of=None,
    reason="", request_context=None,
) -> PostingResult
```

Inputs use typed values and Decimal amounts, with currency, account, description and optional future dimension references on each line. Future module adapters validate source ownership and permissions before using the contract; public clients cannot fabricate a trusted source or approval exemption.

Lifecycle: draft -> validation/preview -> pending approval when required -> posted. Pending financial content is frozen. Rejection/withdrawal permits an explicit new draft revision. Posted content is never reopened for editing. A reversal creates another posted journal with swapped native/base amounts and the original rates, in an explicitly chosen open period; the original remains posted and its reversed label is derived from the link.

Posting in one transaction:

1. Check the actor's current stored permissions and source/action rules.
2. Acquire the shared company financial-settings lock, then locks in a documented consistent order for policy, periods, journal and affected accounts/bank accounts.
3. Resolve the unique posting identity and compare a canonical input fingerprint. Identical retries return the existing result, including after rate changes; conflicting key reuse returns 409. A unique domain source/action key also blocks duplicates under different client keys.
4. Validate dates, open period, active/postable accounts, hierarchy/currency restrictions, at least two meaningful lines, finite nonnegative exact amounts, one side per line and currency precision.
5. Resolve and freeze rates; calculate exact rounded base amounts. Reject any base imbalance unless the user explicitly supplies an identified rounding/FX line.
6. Apply the financial-adjustment policy or attach the approved immutable snapshot. Allocate the journal number under a row lock using the existing numbering template; numbers are unique and never reused for another entry.
7. Persist journal/lines and posting metadata, append the audit event, and commit together. Failures leave no partial posting or completed idempotency record.

Draft updates carry a revision/version check to reject stale edits. API mutation responses distinguish `posted`, `pending_approval` and an idempotent replay.

## 3. Database guarantees and concurrency

Services provide useful error messages; PostgreSQL independently protects accounting invariants:

| Invariant | Database enforcement |
|---|---|
| Valid line amounts | Checks for finite amounts, nonnegative debit/credit, exactly one positive side, positive finite FX rates and valid positions |
| Unique financial identities | Unique posting keys, source/action identity, journal numbers, line positions and reversal target |
| Balanced posted entry | Constraint trigger validates at least two lines and exact equality of base debits/credits at transaction completion |
| Posted immutability | Triggers reject financial header changes and insertion, modification, movement or deletion of posted lines; protected foreign keys retain references |
| Concurrent line editing/posting | Line mutations lock the parent journal; posting validates after acquiring the same lock |
| Open dates and stable account meanings | Posting triggers verify period/date membership and posting eligibility; account guards prevent historical classification, currency or hierarchy reinterpretation |
| No overlapping periods/years | Range exclusion constraints plus containment/date checks; boundary changes are rejected once used |
| Settings versus first posting | Posting and company updates share the company-row lock. A DB guard also rejects base-currency/fiscal-start changes once posting exists |
| Duplicate matches | Unique active statement-line and ledger-line membership plus bank/session row locks, exact currency/amount validation and protected completed matches |

Use targeted posting triggers rather than attaching the unconditional append-only function to editable drafts. Deferred validation allows an atomic multi-line posting while rejecting invalid committed state. Test raw SQL and ORM bypass attempts, not only API calls.

Run concurrency tests with separate PostgreSQL connections and synchronization barriers: repeated/conflicting posting keys, different keys for the same source, duplicate reversal, posting versus close, first posting versus company change, concurrent hierarchy edits, concurrent treasury withdrawals and competing reconciliation matches.

Reference: PostgreSQL 18 [constraint triggers](https://www.postgresql.org/docs/18/sql-createtrigger.html) and [range exclusion constraints](https://www.postgresql.org/docs/18/rangetypes.html#RANGETYPES-CONSTRAINT).

## 4. Money, rates and treasury valuation

- Authoritative amounts: Python Decimal and PostgreSQL `NUMERIC(24,6)`; rates `NUMERIC(30,12)`. Validate actual currency minor units before storage; additional storage scale does not permit invalid fractional currency units.
- Reject float inputs, NaN/infinity, excessive precision, invalid rates and overflow. API financial values are decimal strings. Frontend form values remain strings; exact previews/formatting use BigInt minor units and string conversion rather than Number arithmetic.
- Rate direction: units of base currency per one transaction-currency unit. Base rate is exactly 1. Select the most recent applicable rate at or before the posting date; missing foreign rates fail. An authorized explicit override records its source and reason.
- Round conversion once per line to base currency precision with `ROUND_HALF_UP`. Show residual differences explicitly; never silently add a balancing plug.
- Same-currency transfers debit the destination and credit the source in a single journal. They create no income/expense.
- Cross-currency transfers require both native amounts, applicable rate snapshots and an explicit preview. Remove foreign bank units at their weighted-average historical book value derived from posted lines; recognize the disclosed difference in configured FX gain/loss accounts. Keep rounding distinct from actual FX gain/loss. Full disposal clears the exact remaining book value.
- All foreign-bank outflows use the same valuation path, including manual journal bank lines. Revalidate an approved valuation snapshot if intervening movements make it stale; require resubmission rather than silently changing the approved amounts. Do not support an unvalued foreign overdraft.
- Reversals exactly negate original native/base amounts and rates. New rate records cannot change earlier postings.
- Advanced unrealized revaluation is a documented later enhancement. No external rate feed or banking connector.

## 5. Periods, opening balances and history locks

- Fiscal-year setup generates the expected periods from the configured month. Reject overlaps, gaps within a generated year and inconsistent boundaries. Closing locks posting; reopening requires stronger access, a reason and audit evidence. A closed year cannot retain an open child period.
- Implement `company.services.financial_history_exists()` using committed posted journals and replace its placeholder. Currency/fiscal settings and period setup acquire the same lock as first posting. Existing unused fiscal structures must be deliberately replaced or validated before changing the fiscal start.
- Opening balances use a guided journal at a selected date with all balancing equity/retained-earnings lines visible. An imbalance is rejected. A unique opening source identity prevents duplicate initial loads. Later corrections use linked reversals/adjustments.
- Period closing locks dates; it does not silently zero income/expense accounts or generate retained-earnings postings.

## 6. Approval and permission integration

- Reuse stable `finance.view`, `accounting.manage`, `reports.export` and `approvals.manage` codes.
- Add narrowly scoped `accounting.approve` and `accounting.periods.manage`; grant new sensitive capabilities to Administrator automatically, preserving all existing non-admin/custom role assignments. Administrators explicitly assign them through the existing permission matrix.
- Read financial endpoints require `finance.view`; mutations require `accounting.manage`. Close/reopen controls additionally require `accounting.periods.manage`; reopening requires a reason. Full bank identifiers require the existing `banking.evidence.view`, and ordinary lists remain masked. CSV exports require both finance read and `reports.export`.
- Enable the existing `financial_adjustments` category for manual journals, opening/closed-period corrections, manual bank adjustments and reversals, with its threshold measured by total base debit (not debit plus credit). Ordinary internal transfers retain their own journal/source type and cannot be used to post arbitrary adjustment lines.
- Extend approval uniqueness from `action` to `(action, subject_key)`, defaulting the subject key for existing branding behavior. Different journals may await approval simultaneously; duplicate requests for the same draft revision are rejected.
- Freeze the exact submitted lines, amounts, rates, source and revision/hash. Require the financial approval capability as well as existing designated-role and self-approval rules. The executor calls the posting service inside the decision transaction and rechecks permissions, period status and snapshot validity. Approval-rule administration alone does not grant journal approval.
- Add target links and journal detail/line review to existing requests/notifications, including cache refresh after a decision. Preserve branding approval behavior.
- Use the existing audit service for chart changes, drafts, posting, reversal, rates, treasury operations, periods and reconciliation; record masked bank metadata only.

## 7. Reconciliation

1. Select a bank account and statement date range; enter statement metadata, opening/closing balances and native-currency lines manually.
2. Verify statement arithmetic and date/currency consistency.
3. Show the prototype's statement table and unmatched ledger table with actual balances and candidate matches.
4. Support exact matches and explicit grouped matching of multiple statement/ledger lines whose signed native totals agree. Each line is consumed once; partial allocation of a single line is deferred.
5. The prototype's auto-match action accepts only unique exact candidates under a documented date tolerance, skips ambiguous candidates, and audits the accepted matches. Unmatching is available while open.
6. A statement-only charge/interest line opens a prefilled transaction form. The operator reviews and posts through the accounting engine before any match; statement ingestion never posts automatically.
7. Completion requires no unresolved statement items and an explained reconciliation equation: statement closing balance plus outstanding ledger receipts minus outstanding ledger payments equals ledger native balance. Unpresented ledger movements remain visible as timing differences.
8. Completed sessions/matches are frozen. Reopening requires period-control authority and a recorded reason, preserves earlier completion evidence and does not rewrite journals.

The inspected prototype does not offer statement CSV import. Include manual statement entry now; document CSV ingestion and partial allocations as enhancements.

## 8. Reports and API surface

All report arithmetic uses posted journal lines, including original/reversal pairs exactly once. Each response computes amounts from a consistent database snapshot, with deterministic ordering and server-calculated totals.

- General ledger: account/date/fiscal-period filters, opening/debit/credit/closing totals, chronological running balances calculated before pagination and search, journal links and account hierarchy drill-down. Display balances using the account's normal side and state whether search hides lines without changing the underlying account balance.
- Trial balance: net debit/credit per posting account, hierarchy subtotals without double counting, totals and an exact zero-difference check.
- P&L: revenue, cost of sales, operating/other expenses and profit for the selected dates, with ledger drill-down.
- Balance sheet: assets, liabilities and equity, plus unclosed income/expense balances split into prior-year and current-year earnings using the configured fiscal start. Do not count earnings again when explicit closing journals have already transferred them to equity. Show the exact equation/difference.
- Cash movement: opening, receipts, payments, transfers, explicit FX effects and closing. Eliminate internal transfers from external receipt/payment totals while retaining their account detail. Label it as cash movement; statutory operating/investing/financing classification remains Phase 6.
- Tax position: mapped input/output account balances and manual tax adjustments; no filing or jurisdictional compliance claims.
- Exports: server-generated CSV of authorized reports/ledgers with spreadsheet-formula escaping and the same filters/totals.

Proposed endpoint groups, preserving `/api/v1/`:

| Prefix | Functions |
|---|---|
| `accounting/accounts/` | Setup preview/apply, list/search/tree, create/detail/edit/deactivate, balances |
| `accounting/journals/` | Draft/create/edit, validate, post, detail/history, reverse; idempotency keys on posting actions |
| `accounting/fiscal-years/`, `accounting/periods/` | Generate/list, close, controlled reopen, audit history |
| `accounting/opening-balances/` | Guided validation, draft and post through the same journal service |
| `accounting/exchange-rates/` | Effective-dated rates, add revision, history and conversion preview |
| `accounting/tax-codes/` | Code/mapping revisions and tax-account position |
| `accounting/ledger/`, `accounting/reports/` | Ledger summary/detail, trial balance, P&L, balance sheet, cash movement and CSV |
| `banking/accounts/`, `banking/transactions/` | Metadata, masked detail, GL balances, transfers and other treasury postings |
| `banking/statements/`, `banking/reconciliations/` | Statement entry, match candidates/groups, auto-match, unmatch, completion/reopen |

Use current error envelope, pagination, request IDs, CSRF and OpenAPI. Views/serializers remain thin; services enforce business rules and permissions.

## 9. Frontend and prototype fidelity

Implement the existing ten navigation destinations: overview, bank/cash accounts, transactions, reconciliation, chart of accounts, general ledger, journals, periods, tax and statements. Add detail routes under existing groups, opening-balance setup in journals/accounts, and rate management in Settings -> Currency.

Create feature folders under `frontend/src/features/accounting/` and `features/banking/`, typed API contracts and exact money helpers. Reuse existing UI, auth, form, query-cache and shell components. Keep the executive dashboard and Phases 4-7 explicitly planned.

Observed accounting-specific prototype details:

- Page padding 24/28/56, maximum width 1640px, section gap 18px. Banking KPI tiles have a 180px minimum.
- Overview: six KPIs, 230px month-end balance chart, 200px account-balance donut and recent movements table. Charts consume server-calculated series and show real empty states.
- Chart: type chips, code/name/type/group/balance columns, 520px edit drawer and ledger links. Add hierarchy/summary-account controls within this layout.
- Ledger: period chips; opening/closing metadata; date/reference/narration/debit/credit/running-balance columns.
- Journals: manual/all-source filters, status badges, 900px line-editor drawer, visible debit/credit/difference footer; 500px reversal drawer with date and reason.
- Reconciliation: KPI strip, statement table with match actions, separate unmatched-ledger table. Account/range and completion controls extend the same form/table design.
- Periods: fiscal/closed/current/adjustment KPIs and period/status/count/revenue/expense/closed-by/actions table.
- Statements: P&L, balance sheet, cash movement and trial-balance tabs, date filters, indented account rows, bold totals and exact-balance banners.

Compare key screens side by side in both themes, 264px/64px sidebar modes and mobile layouts. Newly implemented forms need loading/errors, dirty/cancel handling, duplicate-submission protection, keyboard/focus behavior and honest success responses.

## 10. Test isolation and verification

Backend tests continue against their dedicated PostgreSQL test database. Add financial edge cases, direct database mutation tests, report identities and separate-connection transaction/concurrency tests.

For browser tests, add a dedicated per-run E2E database and temporary backend process/container using the existing image inside the `mateerp` Compose project; point the test frontend on `localhost:3100` at it. Parameterize the existing helpers so all Phase 1/2/3 browser fixtures target that same isolated backend. Preserve normal development data/storage. Do not drop/reset databases, remove volumes or introduce another database server. Retain isolated run data for inspection; document its location/lifecycle.

Run all current Phase 1/2 scenarios unchanged in behavior (update only justified phase labels, version assertions or selectors), plus the required Phase 3 scenarios A-Q. Cover Administrator, Accountant, Viewer and restricted users through the real session/CSRF proxy path.

Verification gate:

1. Fresh additive migrations, Django checks and no migration drift.
2. Ruff lint/format and all pytest tests.
3. OpenAPI validation with zero warnings.
4. ESLint, strict TypeScript and all Vitest tests.
5. Production Next.js build and all Playwright workflows against the isolated backend.
6. Financial reconciliation checks and screenshot review.
7. Verify `main`, preserved user files, prototype cleanliness and Docker isolation. Never commit or push.

## 11. Implementation sequence and delivery

1. Introduce models, additive migrations and explicit chart/fiscal setup; preserve all existing data.
2. Build money/rate validation and the central posting service with DB guards and concurrency tests.
3. Add periods, history locks, opening balances, reversals and snapshot-based financial approvals.
4. Implement bank/cash metadata, treasury valuation, transfers and reconciliation.
5. Implement ledger/report selectors, exports and tax mappings; verify mathematical identities.
6. Build prototype-faithful pages and forms against tested APIs, including rate settings and approval review.
7. Run regression, browser and visual verification; correct failures.
8. Update architecture, design reference, development/verification instructions, README and CLAUDE accounting conventions. Add `docs/phase-03-summary.md` and a posting-contract/invariants document; retain earlier phase summaries and user-owned AGENTS instructions.

Final report follows the handover's A-J structure: delivered features, backend/frontend work, accounting invariants, security, actual test counts, UI comparisons, exact limitations, Phase 4 integration contract, Git status and suggested commit message. Stop after Phase 3 for user acceptance.

No material implementation blocker was found. The user explicitly approved this plan before Phase 3 development.
