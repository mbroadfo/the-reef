# The Reef — Automation & CI/CD

## Overview

Seven GitHub Actions workflows drive the entire system. Three handle deployment (infra, backend, frontend). Four handle autonomous trading operations (scanning, analysis, monitoring, reporting). All secrets are injected at runtime via GitHub Secrets — no credentials exist in workflow files.

---

## Workflow Map

```
DEPLOY WORKFLOWS (triggered by push)
├── devops-infrastructure.yml  — dashboard/infra/**
├── devops-backend.yml         — dashboard/backend/**
└── devops-frontend.yml        — dashboard/frontend/**

TRADING WORKFLOWS
├── scanner.yml                — cron: every 5 min (market hours)
├── deep_dive.yml              — workflow_dispatch (ticker parameter)
├── stop_loss_monitor.yml      — cron: every 30 min (market hours)
└── daily_report.yml           — cron: 4:30 PM ET weekdays
```

**Deploy rule**: Never manually trigger `gh workflow run` after a `dashboard/**` push. The push auto-triggers the correct deploy workflow. Running it again causes a double-deploy.

---

## Deploy Workflows

### devops-frontend.yml

Triggers on push to `dashboard/frontend/**`.

```
Steps:
1. npm ci
2. npm run build (Vite production build)
3. aws s3 sync dist/ s3://$REEF_S3_BUCKET --delete
4. aws cloudfront create-invalidation --distribution-id $CF_DIST_ID --paths "/*"
```

The S3 sync deletes removed files (`--delete`). CloudFront invalidation ensures users get the new build immediately rather than serving cached assets.

### devops-backend.yml

Triggers on push to `dashboard/backend/**`.

```
Steps:
1. pip install dependencies into package/
2. zip -r function.zip handler.py package/
3. aws lambda update-function-code --zip-file fileb://function.zip
4. aws lambda publish-version
```

No blue/green deployment — Lambda updates are atomic and the new code is live on the next invocation.

### devops-infrastructure.yml

Triggers on push to `dashboard/infra/**`.

```
Steps:
1. terraform init (partial backend config — bucket/key/region passed explicitly)
2. terraform plan
3. terraform apply -auto-approve
```

State is stored in `s3://reef-tf-state/reef-dashboard/terraform.tfstate`. Partial backend config prevents bucket name from being hardcoded in source.

---

## Trading Workflows

### scanner.yml — Every 5 Minutes

```
Trigger: cron (market hours, Mon–Fri)
Runtime: ~30–60 seconds

Steps:
1. uv run python -m the_reef.main scan
   └── ReefMonitor.scan() → checks 15 tickers
   └── Emits signals: PRICE_BREAKOUT, VOLUME_SPIKE, EARNINGS_UPCOMING,
       NEWS_SENTIMENT, PRICE_DROP, RSI_OVERSOLD, RSI_OVERBOUGHT
   └── Writes signals to MongoDB signals collection
   └── Logs signal summary to Actions output
```

The scanner does not trigger deep dives automatically. High-priority signals are candidates for manual `gh workflow run deep_dive.yml -f ticker=TICKER`.

**Watchlist (15 tickers):**
`NVDA, AMD, AVGO, ARM, TSM, META, PLTR, COIN, MSTR, MARA, HOOD, RKLB, ASTS, TSLA, SMCI`

### deep_dive.yml — On Demand

```
Trigger: workflow_dispatch (ticker parameter required)
Runtime: ~3–5 minutes

Steps:
1. uv run python -m the_reef.main dive ${{ inputs.ticker }}
   └── Selects hunter based on signal_type
   └── Runs 8-task sequential CrewAI pipeline
   └── Apex executes BUY or records PASS decision
   └── Trade + decision written to MongoDB
```

Dispatch example:
```bash
gh workflow run deep_dive.yml -f ticker=NVDA
```

The `signal_type` input is optional. If omitted, defaults to PRICE_BREAKOUT routing (Hunter Shark leads).

### stop_loss_monitor.yml — Every 30 Minutes

```
Trigger: cron (market hours, Mon–Fri)
Runtime: ~30–60 seconds

Steps:
1. uv run python -m the_reef.main monitor
   └── CheckStopLossesTool reviews all open positions
   └── Triggers sell for any position below stop threshold
   └── Writes SELL trade to MongoDB
```

Stop levels are set at position entry by Apex. The monitor enforces them mechanically — no AI deliberation at stop-loss time.

### daily_report.yml — 4:30 PM ET Weekdays

```
Trigger: cron (4:30 PM ET, Mon–Fri)
Runtime: ~60–90 seconds

Steps:
1. uv run python -m the_reef.main report
   └── Snapshots portfolio NAV to portfolio_snapshots
   └── Generates session summary (trades, P&L, positions)
   └── Logs report to Actions output
```

The daily snapshot is what drives the portfolio chart in the dashboard. Without this workflow running, the chart flatlines after seed data.

---

## The Autonomy Loop in Practice

A complete autonomous trading cycle from signal to executed trade:

```
09:35 AM  scanner.yml fires
          └── NVDA: PRICE_BREAKOUT detected (5.2% move, volume 2.3x)
          └── Signal written to MongoDB

09:35 AM  Engineer reviews Actions log (or dashboard signal feed)
          └── Confirms signal warrants analysis

09:36 AM  gh workflow run deep_dive.yml -f ticker=NVDA
          └── Hunter Shark: HIGH conviction — breakout above 52w resistance
          └── Research Shark: FAIR value, earnings beat 3 consecutive quarters
          └── Macro Shark: GO — semis sector strong, VIX below 18
          └── Sentiment Shark: BULLISH — positive analyst upgrades past 48h
          └── Contrarian Shark: worry score 5 — stretched RSI, crowded long
          └── Risk Shark: heat score 4 — portfolio 40% cash, no concentration risk
          └── Wildcard Shark: no special situation
          └── Apex: panel score 7, −1 contrarian = 6 → 75% position
          └── BUY 28 shares NVDA @ $892.40 → $24,987.20

04:30 PM  daily_report.yml fires
          └── NAV snapshot written to portfolio_snapshots
          └── Dashboard chart updated
```

---

## Manual Operations

### Force a deep dive
```bash
gh workflow run deep_dive.yml -f ticker=NVDA
gh workflow run deep_dive.yml -f ticker=TSLA -f signal_type=NEWS_SENTIMENT
```

### Trigger daily report manually
```bash
gh workflow run daily_report.yml
```

### Reset paper portfolio
```bash
gh workflow run daily_report.yml -f command=reset
# or locally:
uv run python -m the_reef.main reset
```

### Seed historical trades
```bash
gh workflow run tools-seed-history.yml
```

---

## Monitoring Workflow Runs

```bash
# List recent runs
gh run list --limit 20

# Watch a specific run
gh run watch

# View logs for a run
gh run view <run-id> --log
```

All workflow failures generate a GitHub notification email. There is no Slack/PagerDuty integration today.
