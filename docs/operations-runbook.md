# The Reef — Operations Runbook

## Quick Reference

```bash
# Portfolio status
uv run python -m the_reef.main status

# Run scanner manually
uv run python -m the_reef.main scan

# Deep dive a ticker
uv run python -m the_reef.main dive NVDA

# Sell a position
uv run python -m the_reef.main sell NVDA
uv run python -m the_reef.main sell NVDA 10   # sell specific share count

# Generate daily report
uv run python -m the_reef.main report

# Reset portfolio to $10,000
uv run python -m the_reef.main reset
```

---

## Dashboard

Live at: **https://reef.broadfoot.consulting**

| Panel | What to look at |
|---|---|
| Portfolio chart | NAV over time; gaps = missing daily snapshots |
| Stat pills | Cash available, total P&L, win rate, open positions |
| Shark Aquarium | Per-shark win rate, trade count, avg P&L |
| Shark Leaderboard | Ranked by performance |
| Recent Trades | Last 8 trades with P&L |
| Activity Feed (right rail) | Surfacing shark per trade, color-coded |
| Market Heat Map | Live sector ETF % change (XLK/XLF/XLV/XLY/XLI/XLE) |

Win rate updates in real time from the `/api/sharks` endpoint, which reads closed SELL trades from MongoDB.

---

## Day-to-Day Operations

### Morning (market open)

The scanner fires automatically every 5 minutes. No action needed unless a signal appears worth investigating. Check the Actions tab for scanner output, or watch the dashboard activity feed.

To check what signals fired overnight or at open:
```bash
gh run list --workflow=scanner.yml --limit 10
gh run view <run-id> --log | grep SIGNAL
```

### During market hours

When the scanner surfaces a signal worth acting on:
```bash
gh workflow run deep_dive.yml -f ticker=NVDA
```

Watch the dive in real time:
```bash
gh run watch
```

The trade (if Apex buys) appears in the dashboard activity feed within ~30 seconds of the workflow completing.

**Mirror to eTrade**: After any BUY or SELL executes in the paper portfolio, mirror it manually in eTrade. The dashboard trade history is the source of truth for what to mirror.

### End of day (4:30 PM ET)

`daily_report.yml` fires automatically. It snapshots the NAV and logs a session summary. If it doesn't fire (holiday schedule, cron miss), trigger manually:
```bash
gh workflow run daily_report.yml
```

A missing snapshot won't break anything but creates a gap in the portfolio chart.

---

## Workflow Failures

### Scanner fails

Usually: API rate limit (yfinance) or MongoDB connection timeout.

```bash
gh run view <run-id> --log
# Retry immediately — scanner is idempotent
uv run python -m the_reef.main scan
```

### Deep dive fails mid-pipeline

CrewAI task failure usually means an LLM API error or token limit. The dive is not re-entrant — restart from scratch.

```bash
gh workflow run deep_dive.yml -f ticker=NVDA
```

Check which shark failed in the Actions log. If it's consistently the same agent, check the LLM API status page.

### Stop loss monitor fails

```bash
uv run python -m the_reef.main monitor
```

If a position should have been stopped but wasn't (workflow missed), check current prices manually and sell if needed:
```bash
uv run python -m the_reef.main sell NVDA
```

### Daily report fails

```bash
uv run python -m the_reef.main report
```

If the snapshot wasn't written, the chart will have a gap for that day. No way to backfill — not worth it.

---

## MongoDB Operations

### Connect (via mongosh or Compass)

Use the `MONGODB_URI` from GitHub Secrets (Settings → Secrets → Actions). Never store this locally.

```bash
mongosh "$MONGODB_URI"
use the_reef
```

### Useful queries

```javascript
// Current positions
db.positions.find({}, { ticker: 1, shares: 1, avg_cost: 1, stop_loss: 1 })

// Recent trades
db.trades.find().sort({ timestamp: -1 }).limit(10)

// Portfolio state
db.portfolio.findOne()

// Per-shark win rates (what /api/sharks computes)
db.trades.aggregate([
  { $match: { action: "SELL" } },
  { $group: {
    _id: "$surfaced_by",
    total: { $sum: 1 },
    wins: { $sum: { $cond: [{ $gt: ["$pnl", 0] }, 1, 0] } },
    total_pnl: { $sum: "$pnl" }
  }}
])

// Recent signals
db.signals.find().sort({ timestamp: -1 }).limit(20)
```

---

## Resetting the Portfolio

Full reset wipes trades, positions, and portfolio state, then re-initializes with $10,000.

```bash
uv run python -m the_reef.main reset
# or
gh workflow run daily_report.yml -f command=reset
```

After reset, re-seed historical trades to restore the leaderboard and chart:
```bash
gh workflow run tools-seed-history.yml
```

Seed is idempotent — safe to run multiple times. It uses buy/sell date pairs to simulate historical NAV progression from $5,000 to ~$10,200 over Dec 2025.

---

## Deployment Operations

### Deploy frontend changes

Push to any file under `dashboard/frontend/**`. The `devops-frontend.yml` workflow fires automatically.

```bash
git add dashboard/frontend/src/components/MyComponent.tsx
git commit -m "fix: something in the dashboard"
git push
# DO NOT run gh workflow run — push already triggers it
```

### Deploy backend changes

Push to `dashboard/backend/**`. Same pattern — push triggers `devops-backend.yml`.

### Deploy infra changes

Push to `dashboard/infra/**`. Triggers `devops-infrastructure.yml` → terraform plan + apply.

Review the plan output in the Actions log before the apply runs. If a change is destructive (e.g., replacing a CloudFront distribution), the plan will show it — cancel the workflow if unexpected.

### Check deployment status

```bash
gh run list --limit 10
```

### Rollback frontend

```bash
git revert HEAD
git push
# devops-frontend.yml redeploys previous version
```

---

## Adding Tickers to the Watchlist

Edit `the_reef/scanner/monitor.py`:

```python
DEFAULT_WATCHLIST = [
    "NVDA", "AMD", "AVGO", "ARM", "TSM", "META", "PLTR",
    "COIN", "MSTR", "MARA", "HOOD",
    "RKLB", "ASTS", "TSLA", "SMCI",
    "NEW_TICKER",  # add here
]
```

Commit and push. The scanner picks up the new ticker on its next cron run.

---

## Key GitHub Secrets

Managed at: `github.com/[your-repo]/settings/secrets/actions`

| Secret | Rotation frequency |
|---|---|
| `MONGODB_URI` | When Atlas password changes |
| `OPENAI_API_KEY` | If compromised / quarterly |
| `ANTHROPIC_API_KEY` | If compromised / quarterly |
| `SERPER_API_KEY` | If compromised |
| `AWS_ACCESS_KEY_ID` | Quarterly or if compromised |
| `AWS_SECRET_ACCESS_KEY` | Quarterly or if compromised |
| `REEF_S3_BUCKET` | Never (static value) |

To rotate a key: update it in GitHub Secrets first, then revoke the old key in the provider console. The next workflow run picks up the new value automatically.

---

## Health Checks

| Check | Command / URL |
|---|---|
| Dashboard live | https://reef.broadfoot.consulting |
| API responding | https://reef.broadfoot.consulting/api/portfolio |
| Lambda healthy | `aws lambda get-function --function-name reef-dashboard` |
| MongoDB connected | Scanner workflow log — first line confirms connection |
| Recent scanner runs | `gh run list --workflow=scanner.yml --limit 5` |
| Portfolio NAV | Dashboard stat pills / `uv run python -m the_reef.main status` |
