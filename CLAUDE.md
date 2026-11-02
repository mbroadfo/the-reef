# The Reef — Claude Code Instructions

## Who You're Working With
The architect behind The Reef — working at the cutting edge of enterprise cloud and AI. Sets architecture, you execute it. Don't explain basics. Don't second-guess decisions unless something is genuinely broken at runtime.

## Project
Reef 2.0: event-sourced paper-trading engine, independent strategy pods (Momentum, Contrarian) in fixed sleeves, deterministic Risk Engine, D0 Apex allocator, React aquarium. Reef 1.0 (CrewAI, Atlas, scheduled workflows) is retired; see docs/reef1-retirement.md. Paper trades mirrored manually in eTrade only once the system proves itself.

## Hard Constraints — Never Violate
- **No .env files** — secrets via GitHub Secrets or environment variables only
- **No stateful data to files or git** — MongoDB Atlas only
- **No broker API** — Apex executes paper trades in The Tank; Mike mirrors manually in eTrade
- **Whole shares only** — `int(position_dollars / price)`, never fractional
- **No LLM calls, Atlas access, deployments or trading activation** without Mike's explicit go-ahead; LLM budget cap is $2/day, $30/month
- **Workflow `name:` fields must be plain ASCII** — emoji breaks GitHub's workflow_dispatch indexing

## Architecture
- **Ledger** — append-only hash-chained events in `the_reef/ledger`; books are derived, never stored
- **Engine** — `advance()` in `the_reef/engine`; Risk Engine in `the_reef/risk`; execution gate in `the_reef/execution`
- **Pods** — `the_reef/pods`, `the_reef/strategy`; Momentum and Contrarian active (30% sleeves each), four asleep
- **Apex** — D0 deterministic allocator, `the_reef/allocation`; dynamic capital allocation is the next milestone
- **UI** — `dashboard/frontend/src/reef2` renders `public/reef2/snapshot.json` built by `tools/build_competition_snapshot.py`
- **Workflows** — `ci.yml` (PR checks) plus three manual, disabled deploy workflows; nothing is scheduled
- **Atlas** — `the_reef` / `the_reef_dev` on `reef-m0` hold Epoch 0 records; nothing in the repo reads them

## Working Style
- Terse responses. No preamble, no trailing summary of what you just did.
- When given an architectural direction, implement it. Don't reopen decisions.
- Flag genuine blockers once, briefly. If Mike confirms, proceed.
- Read `memory/project_reef.md` and `memory/user_mike.md` when starting a session.

## Key Commands
```bash
uv sync --frozen --only-group test --no-install-project
uv run pytest
cd dashboard/frontend && npm ci && npm test && npm run build
PYTHONPATH=. uv run python tools/build_competition_snapshot.py
PYTHONPATH=. uv run python tools/aquarium_demo.py
```
