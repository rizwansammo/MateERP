# Accounting posting contract and invariants

Phase 3. One company per installation. Accounting owns the only authoritative ledger; banking owns metadata and reconciliation, never balances.

## Adapter contract for Phase 4 and later

Call `apps.accounting.services.posting.post_journal` inside the owning domain workflow:

```python
journal = post_journal(
    actor=user,
    posting_key=operation_key,
    source_type="owning_domain",
    source_id=str(source.pk),
    source_action="post",
    posting_date=business_date,
    description="Business narration",
    lines=[
        {"account_id": debit_account.pk, "currency": "BDT", "debit": "100.00"},
        {"account_id": credit_account.pk, "currency": "BDT", "credit": "100.00"},
    ],
    request_context=request,
)
```

Optional inputs: `journal_date`, `draft_id`, `reversal_of`, `adjustment_of`, `reason`. Future adapters validate source ownership, module/operation permission, amount and lifecycle before calling; do not let public clients choose trusted identities. The current generic service additionally requires `accounting.manage`; Phase 4 adapters must deliberately design source-specific permissions rather than exposing a public bypass or automatically granting accounting access to billing roles.

- A source action has one stable `(source_type, source_id, source_action)` identity even across different client keys. Retry identical input to receive the same journal. Reuse with different content is a 409 conflict. Keys are 8–160 characters.
- Check `journal.status`: `pending` is an approval request, **not** a posted financial result. Pending/draft entries do not affect balances. Owning records must distinguish those states and commit their links atomically with journal creation. No Phase 4 owning records exist yet.
- For public drafts use `/api/v1/accounting/journals/` and its `validate`, `post`, `reverse`, `history` actions. Posting returns `{status: posted|pending_approval, journal, replayed}`. A draft update sends its current `revision`; stale edits conflict.
- Public manual sources are manual/opening/adjustment only. One initial opening source is allowed. Adjustment links reference posted entries. Corrections never edit posted content.
- Reject/cancel before editing frozen manual approval drafts. Revalidation saves a new revision and resubmission uses a fresh key. Rejected treasury requests have no ledger effect; record a fresh reviewed transaction. A rejected reversal can be requested again from its original entry.

## Money and rates

- Native/base amount storage: `NUMERIC(24,6)`; rate storage: `NUMERIC(30,12)`. Storage capacity does not override currency precision. Current supported catalog uses zero or two minor units.
- Requests and responses use decimal strings. Floats, booleans, nonfinite/negative amounts, excessive scale, zero-sided lines and simultaneous debit/credit are rejected. One side must be positive per line.
- Rate direction: **base units per 1 foreign unit**. Base rate is exactly 1. Use the most recent revision effective on or before the posting date; explicit overrides need a source/reason.
- Conversion rounds once per line to base minor units with `ROUND_HALF_UP`. Zero-valued conversion is rejected. Cross-currency journals balance exactly in base currency; no silent rounding plug.
- Foreign bank outflows remove weighted-average book value derived from posted lines; full disposal removes the exact remaining book. Native units cannot go negative. Foreign movements must be chronological; same-day order follows actual posting serialization.
- Treasury previews include every balancing FX line and a quote fingerprint. The browser submits that fingerprint at confirmation; changed rates/book values require another preview. Identical posting retries still return the original result after rates change.
- Pending carrying-value outflows are revalidated at approval; intervening changes can require withdrawal and resubmission. Reversals exactly negate the original snapshots and cannot leave an unvalued foreign bank remainder.
- Unrealized FX revaluation, external feeds and foreign overdraft valuation are deferred.

## Transactions, locks and database boundaries

Lock order: singleton company → business settings/policy/approval as needed → journal/period/accounts → bank/reconciliation records. Services acquire the company lock before domain records. All financial changes, source links, numbering and audit evidence commit together. Multi-query financial reports also acquire it; the ledger detail uses one SQL statement and parameterized window queries.

Database protections: posted header/line immutability, deferred exact balance, source/key/number/reversal uniqueness, actual currency precision, valid spot snapshots, active postable account eligibility, protected historical account meaning (including ancestors), account hierarchy, non-overlapping fiscal/period ranges, period containment/closing, company history lock, immutable FX/tax revisions and posting identities, frozen financial approval payloads, single-use active matches and completed reconciliation evidence.

Application authorization remains mandatory. Triggers enforce data invariants; they are not a substitute for permissions or a defense against a database owner deliberately disabling triggers. Audit and posting correctness are covered by direct ORM/SQL bypass tests as well as API tests.

## Periods and reports

Generate twelve monthly periods from the configured fiscal start. Closing locks dates; reopening requires `accounting.manage`, `accounting.periods.manage`, a reason and audit. Closing is not automatic earnings transfer. Posted history locks base currency and fiscal start. Existing unused fiscal years prevent silently changing the fiscal start; no automatic restructuring/deletion is provided.

Reports require `finance.view`; export additionally requires `reports.export`. Balances include posted originals and reversals once each. Trial-balance grand totals exclude displayed hierarchy subtotals. P&L separates cost of sales, gross profit and expenses. Balance sheet derives prior/current unclosed earnings from the configured fiscal start without counting an explicit earnings transfer twice. Cash movement eliminates internal transfers and discloses FX effects; full statutory classifications are Phase 6. Tax position is mapped ledger balances, not a filing engine.

Ledger search hides rows without changing running balance or date-range totals. Ordering is posting date, journal number, line position and ID. CSV preserves selected dates/search and escapes spreadsheet formulas. UI pagination is bounded; large CSV requests should be assessed during Phase 7 load testing.

## Reconciliation

Manually entered signed statement lines must satisfy opening + lines = closing. Statement ranges for a bank are sequential and contiguous. The first opening must equal the ledger before that range; that earlier ledger is the initial reconciliation baseline, not an outstanding receipt. Later openings equal the preceding statement closing. Empty months are supported. Statements never post journals. Exact/grouped matches require the same bank/currency and equal signed native totals; an active line can be consumed only once. Auto-match uses unique equal-amount candidates within five days, skipping ambiguity on either side.

Completion requires every statement line matched and `statement closing + outstanding signed ledger = ledger balance`. Complete earlier statements first. Outstanding ledger items remain timing differences. Completion freezes statement/match evidence and blocks backdated bank postings through the completed date. Reopen with period-management authority and a reason, later statements first; earlier evidence remains. Unmatch before reversing a completed matched transaction.

CSV statement ingestion and partial allocations of one line are intentionally deferred per the approved plan.

## Permissions and future integration

Reads: `finance.view`; writes: `accounting.manage`; close/reopen: also `accounting.periods.manage`. Financial decisions additionally require `accounting.approve` plus designated-role/self-approval rules; full bank identifiers additionally require `banking.evidence.view`. Existing non-admin roles do not receive the two new sensitive permissions automatically.

Phase 4 should implement source adapters, tax application and collision-safe document issuance around this engine; persist source/journal/branding references together; preserve document snapshots; use exact values; and test payment retries and concurrent issuance. Do not add customer/vendor/founder shadow ledgers.
