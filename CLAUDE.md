# The Reef — Claude Code Instructions

## Who You're Working With
Mike is a senior engineer/architect (BSEE + BSCE) working at the cutting edge of enterprise cloud and AI. He sets architecture, you execute it. Don't explain basics. Don't second-guess his decisions unless something is genuinely broken at runtime.

## Project
Autonomous agentic paper trading system. 3-tier shark hierarchy (CrewAI) → MongoDB Atlas → GitHub Actions. Paper trades mirrored manually in eTrade once the system proves itself.

## Hard Constraints — Never Violate
- **No .env files** — secrets via GitHub Secrets or environment variables only
- **No stateful data to files or git** — MongoDB Atlas only
- **No broker API** — Apex executes paper trades in The Tank; Mike mirrors manually in eTrade
- **Whole shares only** — `int(position_dollars / price)`, never fractional
- **No `super().__init__()` in @CrewBase classes** — breaks MRO; use `set_tank()` before instantiation
- **Workflow `name:` fields must be plain ASCII** — emoji breaks GitHub's workflow_dispatch indexing

## Architecture
- **The Tank** — MongoDB-backed paper brokerage, `$10,000` starting bankroll
- **Apex Shark** — Claude Sonnet 4.6, Portfolio Manager, final trade authority
- **Analyst Sharks** — Value, Macro, Contrarian (GPT-4o-mini)
- **Hunter Sharks** — Momentum, Earnings, News (GPT-4o-mini)
- **4 workflows** — scanner (5 min), deep_dive, stop_loss_monitor (30 min), daily_report (4:30pm ET)
- **DB** — `the_reef` (prod) / `the_reef_dev` (dev), cluster `reef-m0`

## Working Style
- Terse responses. No preamble, no trailing summary of what you just did.
- When given an architectural direction, implement it. Don't reopen decisions.
- Flag genuine blockers once, briefly. If Mike confirms, proceed.
- Read `memory/project_reef.md` and `memory/user_mike.md` when starting a session.

## Key Commands
```bash
uv run python -m the_reef.main status
uv run python -m the_reef.main scan
uv run python -m the_reef.main dive TICKER
uv run python -m the_reef.main sell TICKER [SHARES]
uv run python -m the_reef.main report
uv run python -m the_reef.main reset
gh workflow run deep_dive.yml -f ticker=NVDA
gh workflow run daily_report.yml -f command=reset
```
