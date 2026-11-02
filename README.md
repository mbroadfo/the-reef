# The Reef

An event-sourced paper-trading engine in which independent strategy pods compete for capital under one deterministic risk engine, with Apex deciding what each pod is allowed to do. **Everything is paper. Nothing trades, nothing calls a paid API, and the demonstration costs $0.**

The goal is a $0-new-recurring-cost system: it runs from files on a laptop, CI uses no secrets, and no paid LLM calls or services happen without Mike's separate authorization. The $2/day and $30/month LLM cap is a ceiling on what could ever be authorized, not permission to spend.

## What exists today (Reef 2.0)

- **One ledger.** Append-only, hash-chained events (fills, marks, stops, proposals, Apex decisions, sleeve funding). Books and statistics are derived from it, never stored separately. `the_reef/ledger`
- **One engine.** `advance()` runs a session: fill queued orders at the next open, mark at the close, check stops and risk, collect pod proposals, let Apex decide, queue orders. `the_reef/engine`
- **Risk Engine and execution gate.** Whole shares only, position and exposure limits, pauses on daily loss and drawdown, fail-closed on stale or untrusted data. `the_reef/risk`, `the_reef/execution`
- **Pods.** Momentum (Hunter) and Contrarian are active, each in a fixed 30% sleeve of the fund (40% cash). Value, Macro, Earnings and News are registered but asleep and carry no numbers. `the_reef/pods`, `the_reef/strategy`
- **Apex (D0).** A deterministic allocator: fixed sleeve weights, best-ranked idea per pod per session, never more than asked, then the gate and the Risk Engine. No LLM. `the_reef/allocation`
- **Offline history.** Hunter replayed on free daily bars cached locally (survivorship-biased, not evidence of an edge). `the_reef/backtest`, `docs/reef2-hunter-history.md`
- **Aquarium and Research Lab.** A React app that renders one JSON snapshot derived from the ledger: a 70-session replay with no look-ahead, Apex's decision spotlight, team pages, proposal stories, and an in-browser re-verification of the hash chain and every sleeve's books. `dashboard/frontend`

## Run the demo locally

```bash
uv sync --frozen --only-group test --no-install-project   # Python test deps (exchange-calendars, pytest)
uv run pytest                                             # fixtures only: no network, no Atlas, no LLM
cd dashboard/frontend && npm ci && npm test && cd ../..   # snapshot, accounting and no-look-ahead tests
PYTHONPATH=. uv run python tools/aquarium_demo.py         # rebuild the snapshot, serve http://localhost:5173/
```

`tools/build_competition_snapshot.py` regenerates `dashboard/frontend/public/reef2/snapshot.json` byte for byte from the engine. Prices in the demo are synthetic and every page says so.

## Current limitations

- Capital is **not** reallocated between pods yet. Sleeves are fixed; dynamic Apex allocation is the next milestone.
- The demo uses synthetic prices. The real-data replay is a fixed, survivorship-biased universe and proves nothing about skill.
- Only two pods have strategies. No LLM research agents are wired in; the interface exists so one can join without touching Apex, Risk or the ledger.
- No broker API, no scheduled runner, no database. State lives in the ledger events and generated snapshots; private market-data caches stay outside Git. There is no live trading and no trading activation.
- `MONGODB_URI` and Atlas are legacy Reef 1.0 infrastructure pending retirement; Reef 2.0 development and CI do not need them.
- Mike mirrors trades manually in eTrade only if the system proves itself first.

## Reef 1.0 (retired)

The original CrewAI committee, scanner, stop-loss monitor, daily report, Atlas-backed Tank and legacy dashboard were retired in this repository. Their code lives in git history (last state at `f6fdbe1`); the Epoch 0 records stay in MongoDB Atlas, untouched. See [docs/reef1-retirement.md](docs/reef1-retirement.md) for the inventory and what was kept.

## Repository

| Path | Contents |
|---|---|
| `the_reef/` | Engine, ledger, risk, execution, market data interfaces, pods, strategies, allocation, replay, snapshot |
| `tests/` | Pytest suite (fixtures and mocks only) |
| `tools/` | Snapshot builder, demo launcher, offline history fetch and replay, walkthrough |
| `dashboard/frontend/` | Aquarium, team pages, proposal stories, Research Lab (React, Vite, TypeScript) |
| `dashboard/backend/`, `dashboard/infra/` | Reef 1.0 API (Lambda) and Terraform; retained, not exercised. See the retirement doc |
| `.github/workflows/` | `ci.yml` (frontend, backend, tests, terraform, hygiene) and three manual deploy workflows, disabled |
| `docs/` | Reef 2.0 design notes, release management, security and infrastructure notes |
