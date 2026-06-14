# The Reef — System Architecture Overview

## Purpose

The Reef is an autonomous paper trading system driven by an AI investment committee. It scans a curated watchlist for actionable signals, routes high-confidence signals through an 8-agent analysis pipeline, and executes paper trades in a simulated brokerage (The Tank). A live React dashboard provides real-time visibility into portfolio performance, agent activity, and market conditions.

Paper trades are mirrored manually in eTrade once the system demonstrates consistent edge. No broker API is connected — this constraint is intentional and permanent until the system earns it.

---

## Four-Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER                                      │
│  React + Vite + TypeScript + Tailwind CSS               │
│  CloudFront → S3  |  reef.broadfoot.consulting          │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│  API LAYER                                               │
│  AWS API Gateway → Lambda (Python)                      │
│  8 REST endpoints — portfolio, trades, sharks, sectors  │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│  DATA LAYER                                              │
│  MongoDB Atlas M0 (the_reef / the_reef_dev)             │
│  trades · positions · portfolio · signals · decisions   │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│  AI LAYER                                                │
│  CrewAI — 8-shark investment committee                  │
│  Claude Sonnet 4.6 · GPT-4o · GPT-4o-mini              │
│  GitHub Actions — scanner, deep_dive, monitor, report   │
└─────────────────────────────────────────────────────────┘
```

---

## The Autonomy Loop

```
Every 5 min:  Scanner watches 15 tickers
                 │
              Signal detected (PRICE_BREAKOUT, VOLUME_SPIKE, etc.)
                 │
              Signal written to MongoDB
                 │
              deep_dive.yml triggered (workflow_dispatch or manual)
                 │
              8-shark pipeline runs (~3–5 min)
                 │
              Apex Shark: BUY / HOLD / PASS
                 │
         BUY → ExecuteBuyTool → position written to MongoDB
                 │
         Every 30 min: stop_loss_monitor checks open positions
                 │
         4:30 PM ET: daily_report summarizes session
```

---

## Technology Choices

| Concern | Choice | Why |
|---|---|---|
| AI orchestration | CrewAI | Sequential task pipeline with typed context passing |
| LLM routing | 3 models (see below) | Cost/capability match per role |
| State | MongoDB Atlas | JSON-native, no schema migrations, free M0 tier |
| Compute | AWS Lambda | Zero idle cost, scales to zero between runs |
| CDN | AWS CloudFront | Global edge, TLS termination, S3 origin |
| IaC | Terraform | Declarative, state in S3, reproducible |
| CI/CD | GitHub Actions | Integrated with code, secrets managed natively |
| Frontend | React + Vite | Fast builds, TypeScript safety, Tailwind for speed |

### LLM Routing Strategy

Three models are used, matched to role complexity and call frequency:

- **GPT-4o-mini** — Hunter Shark only. High-frequency technical screening, low cost per token.
- **GPT-4o** — Research, Macro, Sentiment, Wildcard. Deep analysis requiring strong reasoning.
- **Claude Sonnet 4.6** — Contrarian, Risk, Apex. Final authority roles requiring nuanced judgment and tool use.

---

## Cost Model

The system is designed to run indefinitely at near-zero fixed cost.

| Component | Cost |
|---|---|
| MongoDB Atlas M0 | Free |
| AWS Lambda | ~$0 (well within free tier) |
| API Gateway | ~$0 (low request volume) |
| CloudFront | ~$0–$1/month |
| S3 (state + frontend) | <$1/month |
| GitHub Actions | Free (public repo minutes) |
| LLM API calls | ~$0.10–$0.50 per deep dive |
| **Total fixed** | **<$5/month** |

Variable cost is LLM inference per trade signal. A system running 2–3 deep dives per day costs roughly $15–45/month in API tokens at current pricing.

---

## Databases

Two MongoDB databases on cluster `reef-m0`:

- `the_reef` — production
- `the_reef_dev` — development / testing

Collections: `trades`, `positions`, `portfolio`, `portfolio_snapshots`, `signals`, `decisions`

All state lives in MongoDB. No state is written to files or git. The paper brokerage starts with a $10,000 bankroll; positions and cash are tracked in the `portfolio` collection.

---

## Deployment Topology

```
GitHub (source of truth)
    │
    ├── dashboard/frontend/** → devops-frontend.yml → S3 + CloudFront invalidation
    ├── dashboard/backend/**  → devops-backend.yml  → Lambda zip deploy
    ├── dashboard/infra/**    → devops-infrastructure.yml → Terraform apply
    └── tools/seed_history.py → tools-seed-history.yml (manual only)

Trading workflows (cron + dispatch):
    ├── scanner.yml          — every 5 min during market hours
    ├── deep_dive.yml        — workflow_dispatch, ticker parameter
    ├── stop_loss_monitor.yml — every 30 min during market hours
    └── daily_report.yml     — 4:30 PM ET weekdays
```

Custom domain: `reef.broadfoot.consulting` via Cloudflare DNS (CNAME to CloudFront, unproxied).
