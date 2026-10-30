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
| Immutable | events are frozen; each hash covers `seq`, the previous hash and the content fingerprint |
| Tamper and gap detection | `replay` and `Ledger(store)` re-verify the whole chain on load |
| Idempotent fills | `event_id` = digest(epoch, sleeve, order id); same content again -> `DUPLICATE`, nothing written; different content -> `ConflictError` |
| Idempotent corporate actions | `event_id` is `CashOut.event_id` (action id + holder); `Ledger.settle_corporate_actions` is safe to call every session and after a restart |
| Atomic | an event that fails validation changes nothing and is not stored |
| Deterministic replay | `LedgerState.digest()` and the head hash are equal across independent builds and replays; a prefix replays to the state at that point |
| Time order | `occurred_at` may not go backwards |

## Boundaries to the rest of the Reef

- `views.fund_view` builds the Risk Engine's `PortfolioView` from the ledger: all sleeves aggregated (caps are fund-wide), stops carried, so per-position stop-risk sees every sleeve. A missing or invalid mark carries the position at cost and sets `book_trusted=False` (blocks entries, never exits; defect E-6).
- `Ledger.settle_corporate_actions` consumes `settlements_due` (point-in-time, per holder).
- Fills are appended by the future `advance()` step after the gate accepts them; the ledger does not re-check market hours or tradability (that is the gate's job) but does enforce its own accounting rules.

## Not in this slice

Database adapter (unique indexes on `event_id` and `seq`), snapshots for fast load, fees and slippage, dividends and splits, sleeve-to-sleeve transfers (always via fund cash), the shadow D1-D3 books (separate ledgers on the same inputs), allocator logic, and `advance()`.
Note: the sequence-number check in `apply` is defensive; the hash chain already catches gaps and reordering.

## Requirements recorded for later slices (Mike, 2026-10-31)

1. A configurable portfolio-wide aggregate stop-risk budget (total open stop-risk across all positions) in the Risk Engine and `RiskLimits`. Today the budget is per position only.
2. Production-quality point-in-time market-data adapters: instrument master, corporate actions and prices that can answer `as_of` queries without leaking later knowledge, and that refuse queries they cannot answer.
