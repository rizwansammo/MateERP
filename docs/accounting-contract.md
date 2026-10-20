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

Phase 4 implements source adapters, exact tax application and collision-safe document issuance around this engine. Do not add customer/vendor/founder shadow ledgers.

## Phase 4 source ownership and settlement

- A `PostingAuthority` is bound to the authenticated actor, registered source and action after checking current database permissions. It is internal and cannot be supplied through API JSON. `accounting.manage` alone does not authorize issuing invoices or verifying customer payments.
- Invoice drafts/orders have no AR effect. Approved issuance freezes business lines, taxes, customer/company identity, historical rate, document number and published branding reference in the same transaction as AR/revenue/tax posting. Void uses the owning domain's guarded reversal, never a direct manual ledger edit.
- Recorded customer payments reserve proposed allocations but remain unposted. A different authorized verifier rechecks available balances, periods, FX and approval policy. Only verification creates the payment journal and official receipt. Reversal reopens allocations and cancels the receipt while retaining its original PDF.
- AR settlements consume each invoice's original base carrying value; customer advances/credit notes create explicit credit movements. Credit application moves liability to AR without moving cash. Refunds move cash and consume available credit; they are distinct from credit notes. Historical credit valuation and FX differences remain auditable.
- Posted vendor bills and accrued expenses create AP; immediately paid expenses debit expense/input tax and credit the selected bank. Vendor payments validate exact allocations and supplied quote fingerprints. Nonzero FX requires a current preview fingerprint and explicit acceptance. Approval freezes that quote and rechecks it against current carrying values; changed values require rejection and resubmission, never silent reconfirmation. Foreign bank outflows obey existing carrying-value, chronology and reconciliation guards.
- `/billing/reconciliation/` independently compares invoice/credit source totals with AR/customer-credit GL controls. `/purchasing/reconciliation/` independently compares bills/accrued expenses and settlements with AP. Differences must equal exact zero. There are no independent bank balances or second posting engine.
- Control accounts must be postable, correctly typed, unique by purpose and unused when designated. Existing historical balances are not silently relabeled as a subledger. Configure migration/opening plans deliberately; Phase 4 migrations do not create financial records.
- All financial services take the company lock first and use atomic transactions. Unique source/action identities, stable client keys, canonical payload fingerprints, numbered sequences and database guards protect concurrent retries. Changed payloads under the same key are rejected. Credit requests predating fingerprint migration retain history; their blank identities are not guessed/backfilled, so an attempted replay returns a conflict and must be reviewed using the existing record.
- Issued project billing locks customer, currency and contract value. Profitability sums historical posted revenue and expense values in base currency across all source currencies, excluding recoverable tax and capitalized assets. Native project totals are separate from this base-currency measure.

## Official documents and recovery

Issued invoices/credit notes/receipts retain immutable snapshots and a published `BrandingVersion`. The original ready PDF, SHA-256 metadata and stable file ID are preserved. Current company/branding changes cannot rewrite an issued document. Rendering failure leaves an issued/posted record with a failed/pending PDF state; retry its PDF action to render the frozen snapshot, never submit another issue/payment to recover a file.

Client filing follows invoice issue year even for later collections. Multi-invoice receipts reference the same stored PDF from each invoice bundle. Vendor filing follows document year/month/vendor/type. Generated PDFs cannot be refiled or archived; uploaded evidence can be archived with a reason while its private file and audit history remain. Metadata and download access both enforce reference/purpose permissions, including the separate bank-evidence permission.

Recurring invoices default to drafts; auto-issue requires explicit authorization that is rechecked on every run. Recurring expenses generate drafts for review. Schedule/date uniqueness and row locks prevent duplicate occurrences. Failed runs can be retried, and owner permission revocation prevents unauthorized unattended processing. Phase 5 founder settlements and Phase 6 purchase orders remain outside this implementation.
