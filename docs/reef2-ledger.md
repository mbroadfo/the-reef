# Reef 2.0 Foundation Slice 2: event-sourced portfolio ledger

One fund ledger per epoch. State is never edited: it is the replay of an append-only, hash-chained event log. `the_reef.ledger` has no database, clock, network or model access; persistence is a port (`EventStore`) with an in-memory implementation for now.

## Model

- **Epoch**: opens with all cash (`EPOCH_OPENED`), one active at a time, closed epochs reject every event, positions never carry over. Epoch 0 (Reef 1.0) is an archive and is not replayed here.
- **Fund and sleeves**: the fund holds unallocated cash plus independent virtual sleeves (one per shark or pod). Cash moves between fund and sleeve only through `SLEEVE_FUNDED` (signed). A sleeve cannot spend more than its own cash, cannot sell what it does not hold (no shorting), and cannot touch another sleeve's positions.
- **Events**: `EPOCH_OPENED/CLOSED`, `SLEEVE_CREATED`, `SLEEVE_FUNDED`, `FILL`, `STOP_UPDATED`, `CORPORATE_ACTION_SETTLED`. Whole shares only; money is `Decimal`, serialized as strings.
- **Cost basis**: average cost. Partial sells remove cost pro rata, rounded to 8 dp with half-even; a full sell removes the exact remainder, so realized P&L sums exactly.
- **Invariant** (checked after every append in tests): `unallocated + sum(sleeve cash) + sum(position cost) == initial cash + sum(realized P&L)`; no negative cash; no non-positive position.

## Guarantees

| Property | Mechanism |
|---|---|
| Immutable | events are frozen and their payloads deep-frozen (defensive copy: read-only mappings, tuples), as are the state containers; each hash covers `seq`, the previous hash and the content fingerprint |
| Tamper, gap, reorder detection | `replay` and `Ledger(store)` re-verify the whole chain on load |
| Tail truncation / full re-chain | NOT detectable from the chain alone. Detected only against an independently preserved `Checkpoint` (`Ledger(store, expected=cp)` -> `TruncationError`); see the store contract below |
| Idempotent fills | `event_id` = digest(epoch, sleeve, order id); same content again -> `DUPLICATE`, nothing written; different content -> `ConflictError` |
| Idempotent corporate actions | `event_id` = digest(action id, epoch, sleeve), derived in one place and re-derived by the ledger on apply (a supplied id is rejected); unique per epoch, sleeve and action. `settle_corporate_actions` is safe to call every session and after a restart |
| Settled history is not rewritten | later changes to an already-settled action (cash terms, withdrawn, re-identified) never re-settle or alter the books; `Ledger.settlement_discrepancies(source, as_of)` reports them (`CASH_CHANGED`, `ACTION_MISSING`). Correction is a new explicit event decided by a human |
| Atomic | an event that fails validation changes nothing and is not stored |
| Deterministic replay | `LedgerState.digest()` and the head hash are equal across independent builds and replays; a prefix replays to the state at that point |
| Time order | `occurred_at` may not go backwards |

## Persistent-store contract (future adapter)

1. Append-only; unique indexes on `seq` and `event_id`; no update or delete.
2. Atomic, strictly sequential appends (`seq` = previous + 1, `prev_hash` = previous hash).
3. After every append the new `Checkpoint(seq, head_hash)` is recorded outside the event collection, with separate credentials or in a separate system (for example the daily report and a write-once object). The load path passes the last preserved checkpoint to `Ledger(store, expected=...)`.
4. On load: full replay, then `TruncationError` if the store is shorter than the checkpoint or its hash at that sequence differs. A longer store is accepted (the checkpoint write may lag one append); the caller then records the new checkpoint.
5. Without an independently preserved checkpoint, tail truncation and a consistent re-chain are undetectable by design.

## Boundaries to the rest of the Reef

- `views.fund_view` builds the Risk Engine's `PortfolioView` from the ledger: all sleeves aggregated (caps are fund-wide), stops carried, so per-position stop-risk sees every sleeve. A missing or invalid mark carries the position at cost and sets `book_trusted=False` (blocks entries, never exits; defect E-6).
- `Ledger.settle_corporate_actions` consumes `settlements_due` (point-in-time, per holder).
- Fills are appended by the future `advance()` step after the gate accepts them; the ledger does not re-check market hours or tradability (that is the gate's job) but does enforce its own accounting rules.

## Not in this slice

Database adapter (unique indexes on `event_id` and `seq`), snapshots for fast load, fees and slippage, dividends and splits, sleeve-to-sleeve transfers (always via fund cash), the shadow D1-D3 books (separate ledgers on the same inputs), allocator logic, and `advance()`.
Note: the sequence-number check in `apply` is defensive; the hash chain already catches gaps and reordering. Average-cost accounting is kept for now.

## Requirements recorded for later slices (Mike, 2026-10-31)

1. A configurable portfolio-wide aggregate stop-risk budget (total open stop-risk across all positions) in the Risk Engine and `RiskLimits`. Today the budget is per position only.
2. Production-quality point-in-time market-data adapters: instrument master, corporate actions and prices that can answer `as_of` queries without leaking later knowledge, and that refuse queries they cannot answer.
