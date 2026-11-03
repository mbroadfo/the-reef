# Live-data paper trading

The existing Momentum and Contrarian sharks, Apex D0 + C1 and the Risk Engine, run day after day on real daily bars with paper money.
Same engine, same strategies, same limits. $0 recurring cost: free Yahoo daily bars through `yfinance`, local files, no broker, no LLM.

**Status: built, not activated.** No epoch exists, no task is scheduled, nothing has touched the real cache or the network except a read-only readiness check.

## Setup (once)

```bash
uv sync --frozen --only-group test --no-install-project      # tests
uv sync --group data                                          # adds yfinance for the data refresh
# optional but recommended: keep checkpoints somewhere the ledger's disk does not hold
setx REEF_CHECKPOINT_DIR "D:\reef-checkpoints"                # another drive or a synced folder
```

Files live outside the repository (`..\the_reef_private\live` by default, override with `REEF_LIVE_DIR`):

| Path | Contents |
|---|---|
| `market/` | the live bar cache: a seeded copy of the research cache plus vetted incremental rows, `manifest.json`, `ingest.jsonl`, `holds.jsonl` |
| `epochs/<id>/ledger.jsonl` | the append-only event ledger (the only state), `ledger.lock` |
| `<checkpoints>/checkpoints/<id>.jsonl` | independent head records, each chained to the one before |
| `<checkpoints>/backups/<id>/` | a copy of the ledger after every run that appended |
| `snapshots/<id>/snapshot.json` | generated UI snapshot (vendor prices: private) |
| `dashboard/frontend/public/reef2/live/` | gitignored copy served to the local UI |

## Commands

```bash
uv run --group data python tools/live.py check                       # one-command readiness (read-only)
uv run --group data python tools/live.py seed                        # copy warmup history into the live cache
uv run --group data python tools/live.py activate --confirm <epoch>  # MANUAL, approved step: opens the epoch
uv run --group data python tools/live.py run                         # manual startup / daily run (safe to repeat)
uv run python tools/live.py status | reconcile | snapshot
cd dashboard/frontend && npm run dev        # http://localhost:5173/live/  (synthetic demo stays at /)
```

`activate` without the typed `--confirm <epoch-id>` refuses. The epoch id is `live-paper-<first session>`; the first session is the first one that opens after activation, so
nothing is backfilled. `run` exit codes: 0 up to date or advanced, 1 error, 2 SAFE_HOLD (a human must look), 3 waiting for data, 4 not activated, 5 another runner holds the lock.

Scheduling (not installed, needs approval): `tools\windows\Register-ReefLiveTask.ps1` is a dry run by default; `-Install` creates the task, `-Remove` deletes it. The runner needs no
scheduler to be correct: run it by hand whenever you like.

## What the epoch is

* `live-paper-<date>`, $10,000, sleeves funded 30 / 30 with 40% in Apex's reserve (`d0-initial`). The synthetic demonstration (`epoch-1`), Epoch 0 and every historical ledger are untouched.
* Two active sharks only. A `CHARTER` attestation in the ledger records strategy hashes, limits, D0, C1 and data rules at activation. Every run compares the code to it; any difference is a SAFE_HOLD.
* Decisions are recorded from the close of the first session. Warmup bars (160 required) feed indicators only; no historical paper trade is invented.

## Execution semantics: reconstructed, not live

Basis `SIMULATED_FROM_DAILY_OHLC`, written into the charter and every session attestation and shown on every page.

* A session is processed only after its bar is final (30 minutes after the close, early closes included) and complete (benchmark present, at least 95% of the universe, held and ordered names given a 3 hour grace).
* Decide at the close, fill at the next session's official open (the bar's open), exits first. A stop that the open gaps through fills at the open; an intraday touch fills at the stop price, from the bar's low. Both are reconstructions: daily bars cannot say what an intraday order would have got.
* No slippage or fees (`ExecutionCosts()` default); the cost model is in the charter and a change would be a drift.
* If the open or close for a name is missing, the order is refused (`NO_VALID_OPEN_PRINT`) or the name is unmarked and new exposure is blocked. Nothing is carried forward or estimated.
* `occurred_at` is the market-clock position of an event; each session's `SESSION_DATA` attestation holds the wall-clock `processed_at`, whether it was a catch-up, and the digest of the bars used.

## Data pipeline

`refresh` appends only bars that pass every check, never overwrites a stored row, and is idempotent. Refused rows are logged (`ingest.jsonl`), not stored.

| Condition | Result |
|---|---|
| Row not yet final, not a session, bad OHLC, zero volume | refused; a not-final row is simply fetched again later |
| Vendor restates a stored bar (more than 5 bp) | stored row kept; symbol on `RESTATED` hold from that bar's close |
| Split day (`Stock Splits` set) | row refused; `SPLIT` hold; nothing later stored for the symbol |
| Close-to-close jump over 40% | refused and held, unless the name is held in a sleeve (then stored and flagged so its stop still sees it) |
| 3 consecutive sessions without a bar while SPY traded | treated as halted (`NO_DATA`) |
| Ex-dividend on a held name | logged and shown; **not credited** (the ledger is price-return) |

A held symbol is `HALTED` to the instrument master, so the existing gate refuses entries and the engine suppresses its signals with an `OPPORTUNITY_SUPPRESSED` record. A `SPLIT` or `RESTATED` hold on a name a sleeve **holds** stops the whole run (SAFE_HOLD): the books and the vendor's prices no longer agree and a human must decide.

## Reconciliation

`live.py reconcile` checks: chain and preserved checkpoints; checkpoint log self-chain; code vs charter; every fill and mark follows its session attestation; the cache still hashes to each session's recorded digest; cache manifest; the snapshot's own five checks; the published snapshot vs the ledger (event by event, NAV, positions); the UI copy.

## Validation

`tests/live/` (run with `uv run pytest tests/live`):

| Requirement | Tests |
|---|---|
| multi-day operation, holidays, early close | `test_multi_day_run_follows_the_exchange_calendar` (Thanksgiving closed, 2026-11-27 marked at 18:00 UTC) |
| persistence across restart | `test_restart_in_the_middle_continues_to_the_same_ledger` (identical head hash) |
| skipped-day catch-up | `test_skipped_days_are_caught_up_in_order...` (identical decisions, flagged `catch_up`) |
| duplicate prevention | `test_running_again_appends_nothing...`, `test_a_second_runner_is_turned_away...` |
| crash recovery | `test_a_crash_in_the_middle_of_a_session_resumes...` (torn line at four points, same ledger as uninterrupted) |
| stale data | `test_stale_data_is_rejected_until_the_vendor_publishes`, `test_data_that_is_not_final_yet_is_not_used` |
| missing open / close | `test_a_missing_open_print...`, `test_a_missing_close_leaves_the_name_unmarked...` |
| splits, dividends | `test_a_split_in_a_held_name_is_a_safe_hold...`, `..._not_held_...`, `test_dividends_on_held_names...` |
| no look-ahead | `test_future_bars_in_the_cache_cannot_leak_into_a_decision` |
| ledger / snapshot reconciliation | `test_reconcile.py` (healthy, edited snapshot, contradicted event, stale snapshot, edited cache, truncated ledger) |
| no tuning | `test_the_live_epoch_runs_exactly_the_competition_configuration` |
| UI | browser-side verifier accepts a live snapshot (`test_ui_contract.py`); `/live` rendered with 0, 1 and 12 sessions |

All data in tests is synthetic. The only network call ever made during development was a read-only fetch of two symbols to confirm the `yfinance` column handling.

## Before activation (decisions and gaps)

1. **Your approval to activate**, and a first session date. Activation is one command and cannot be undone except by closing the epoch.
2. **Checkpoint location.** Until `REEF_CHECKPOINT_DIR` points elsewhere, tail truncation is undetectable by design (the readiness check warns).
3. **Install `yfinance`** (`uv sync --group data`), run `seed`, then one `run` while the market is closed to pull the days since 2026-10-30 and verify against the vendor.
4. **Held-name splits need a human, with no tooling yet.** A SAFE_HOLD stays until a decision; there is no split-adjust or hold-release event. Likelihood is low in this large-cap universe; the fix is a signed correcting event in a later PR.
5. **No point-in-time corporate-action feed at $0.** Pending cash acquisitions are not known in advance (the SEM lesson). Mitigation here is the 3-silent-session halt rule only.
6. **Dividends are not credited** (price-return). Small, disclosed, shown in the UI.
7. **Zero slippage and fees.** Decide whether a cost model belongs in the charter before the epoch starts; it cannot change afterwards.
8. **Yahoo terms are personal use.** The live snapshot holds vendor prices: keep it local, never deploy it. Deploy workflows remain disabled.
9. **Yahoo can silently change or fail.** Restatement, gap and coverage checks are the guard; a long outage just leaves the runner WAITING.
10. **The universe is the survivor-biased 95-name research list.** Fine for operating the system; not evidence of skill. The first reviews fall at sessions 15, 25, 35.
