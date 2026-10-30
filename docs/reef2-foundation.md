# Reef 2.0 foundation (Slice 1)

Pure, tested building blocks for the future `advance(session T)` loop. Nothing here calls a model, a broker or a database, reads a clock, or runs on a schedule. Everything takes explicit inputs and returns a decision with a stable reason code.

## Packages

| Package | Purpose |
|---|---|
| `the_reef.market.calendar` | `MarketCalendar` interface, `ExchangeCalendar` (NYSE via `exchange_calendars`), `StaticCalendar` for fixtures. `classify` an instant as regular / pre-market / after-close / weekend / holiday, `next_valid_open`, fail-closed `CalendarRangeError` outside the known range |
| `the_reef.market.instruments` | `InstrumentMaster` and `CorporateActionSource` interfaces, strict `normalize_symbol`, `check_tradable` (unknown, halted, delisted, acquired, not yet listed, pending cash deal, insufficient history), `settlements_due` (cash-out of a held name from the filed per-share price) |
| `the_reef.market.quotes` | `Quote` with source and timestamp, `validate_quote`, `validate_fill_quote` (official open of the fill session), `mark_close` (a failed mark is UNMARKED, never a carried price), `book_trust` |
| `the_reef.risk` | `RiskLimits` (validated, provisional values) and pure `size_order`, `evaluate_entry`, `evaluate_exit`: pauses (daily loss, drawdown, untrusted book) block entries only; limits clamp and never redistribute; the allocator ceiling can only lower a size |
| `the_reef.execution.gate` | `GatePorts` (the dependencies the loop injects), `queue_order` (decide at the close, fill at the next valid open), `fill_at_open`, `immediate_fill_allowed` |

## How the future loop uses it

1. Step 1 calendar: `classify` / `calendar.session(day)`.
2. Step 3 fill: `fill_at_open(ports, queued_order, official_open_print, portfolio, sleeve_cash)`.
3. Step 5 mark: `mark_close` per holding, then `book_trust`.
4. Step 6 risk state: `pause_reasons`.
5. Step 8 decide: `queue_order(ports, order_intent)`.

## Tests

`pytest` runs on fixtures and mocks only (cached NYSE sessions for 2026-06 to 2026-12 in `tests/fixtures/nyse_2026_h2.json`, an agreement test against the library, SEM facts from SEC filings). Regression tests in `tests/regression/` reproduce the four Reef 1.0 execution defects: an after-close fill (E-1), a holiday fill (E-2), a price with no timestamp or source and an unmarkable holding (E-5, E-6), and a buy of a stock already acquired and delisted (E-9).

## Interface contracts added in review

- **Point in time.** `InstrumentMaster.get(symbol, as_of)` and `CorporateActionSource.actions_for(symbol, as_of)` return only what was known at `as_of`. Records carry a vintage (`InstrumentRecord.as_of`) and actions carry `known_at`; both must be timezone-aware. The gate judges an order on decision-time knowledge when queueing and on the fill-session open when filling. A live-data adapter that cannot answer point-in-time must refuse the query, not return today's record. A known cash deal that is already effective blocks trading even if the master has not caught up.
- **Stop-risk is per position.** The 0.5% risk budget covers the whole position: an add gets `budget - existing stop-risk` (existing shares x (mark - their stop)). A held position with no recorded stop counts as a total loss, so it cannot be added to. Not included: a portfolio-wide cap on total open stop-risk, because no limit for it has been approved.
- **Settlement identity.** `CorporateAction.action_id` hashes symbol, kind and effective date (not cash terms or evidence), so restated or duplicated source rows keep one identity. `CashOut.event_id` = digest(action_id, holder) is the ledger idempotency key; `settlements_due(..., already_settled=ids)` skips ids the ledger has recorded. `CashOut.fingerprint` lets the future ledger detect the same id arriving with a different payload and fail loudly. The ledger itself is not built.

## Slice 3: the Hunter vertical slice

`the_reef.engine.advance` runs one trading session through every foundation piece; `the_reef.strategy` (interface and `Hunter`), `the_reef.allocation.d0`, `the_reef.market.bars` (point-in-time daily bars) and `the_reef.performance` complete it. See `docs/reef2-hunter-walkthrough.md` for a generated end-to-end example, and what is real, simulated and still missing.
