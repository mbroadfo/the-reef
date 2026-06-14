# The Reef

An autonomous paper trading system powered by an AI investment committee. Eight specialized agents — each running a different large language model — debate every trade before Apex Shark makes the final call. The entire system runs on serverless infrastructure for under $15/month, with zero idle compute and no secrets anywhere in code.

**Live dashboard:** [reef.broadfoot.consulting](https://reef.broadfoot.consulting)

---

## How It Works

The Reef runs a continuous loop during market hours:

1. A **scanner** watches 15 high-volatility tickers every 5 minutes, detecting breakouts, volume spikes, earnings setups, and sentiment shifts
2. A strong signal triggers a **deep dive** — an 8-agent CrewAI pipeline where each specialist analyses the ticker in sequence, each reading the full output of everyone before them
3. **Apex Shark** synthesizes the committee into a panel score (0–9), sizes the position, and executes the paper trade — or passes
4. Open positions are monitored every 30 minutes for stop-loss triggers
5. At 4:30 PM ET, a daily report snapshots the portfolio NAV and summarizes the session

Everything runs on GitHub Actions. Nothing runs when the market is closed.

---

## The Investment Committee

Eight sharks, three LLMs, one decision:

| Shark | Model | Role |
|---|---|---|
| Hunter Shark | GPT-4o-mini | Technical breakouts and volume — the tip of the spear |
| Research Shark | GPT-4o | Fundamentals, valuation, earnings calendar |
| Macro Shark | GPT-4o | Sector flows, rates, VIX — GO / CAUTION / AVOID |
| Sentiment Shark | GPT-4o | News narrative and positioning — BULLISH / NEUTRAL / BEARISH |
| Contrarian Shark | Claude Sonnet 4.6 | Steelman bear thesis, worry score 1–10 |
| Risk Shark | Claude Sonnet 4.6 | Portfolio heat score, concentration, stop audit |
| Wildcard Shark | GPT-4o | Crypto-correlated plays, special situations, outlier thesis |
| Apex Shark | Claude Sonnet 4.6 | Portfolio Manager — panel scoring, sizing, execution |

The model routing is intentional: GPT-4o-mini for high-frequency cheap screening, GPT-4o for deep analysis, Claude for the roles requiring adversarial judgment and tool use. → [Full committee spec](docs/ai-investment-committee.md)

### Panel Scoring

Apex scores the committee output on a 0–9 scale before sizing:

- **Hunter** HIGH=+3, MED=+2, LOW=+1
- **Research** CHEAP=+3, FAIR=+2, EXPENSIVE=+0
- **Macro** GO=+3, CAUTION=+1, AVOID=+0
- **Contrarian modifier**: worry 5–6 = −1, 7–8 = −2, 9–10 = −3

Position size follows the score: 7–9 full, 5–6 at 75%, 3–4 at 50%, 1–2 at 25%, 0 = pass. Risk heat further scales down if the portfolio is running hot. Whole shares only.

---

## Stack

```
AI layer:       CrewAI  ·  Claude Sonnet 4.6  ·  GPT-4o  ·  GPT-4o-mini
Data:           MongoDB Atlas M0 (free)
Compute:        AWS Lambda  ·  API Gateway
CDN:            AWS CloudFront  ·  ACM TLS
IaC:            Terraform  ·  S3 state backend
CI/CD:          GitHub Actions (7 workflows)
Frontend:       React  ·  Vite  ·  TypeScript  ·  Tailwind CSS
```

**No EC2. No containers. No idle cost.** The system costs nothing when the market is closed and roughly $0.50–$1.00 per day in LLM inference when running 2–3 deep dives. Total monthly spend: ~$13. → [Infrastructure detail](docs/serverless-infrastructure.md)

---

## Security

- **No secrets in code or files** — ever. All credentials live in GitHub Secrets, injected at workflow runtime
- **No broker API** — `ExecuteBuyTool` writes to MongoDB, not to eTrade. Paper trades are mirrored manually until the system earns real capital
- **IAM least privilege** — the CI/CD user can update Lambda and sync S3; it cannot touch IAM, access other buckets, or read GitHub Secrets via AWS
- **TLS everywhere** — browser → CloudFront → API Gateway → Lambda → MongoDB Atlas; no unencrypted path exists

If every credential were simultaneously compromised, no real money is at risk. → [Security design](docs/security-design.md)

---

## Automation

Seven GitHub Actions workflows — push triggers handle all deploys, cron handles all trading operations:

```
Push dashboard/frontend/**  →  Vite build → S3 sync → CloudFront invalidation
Push dashboard/backend/**   →  Lambda zip → function update
Push dashboard/infra/**     →  Terraform plan + apply

Cron (every 5 min)          →  scanner.yml
workflow_dispatch            →  deep_dive.yml  (ticker parameter)
Cron (every 30 min)         →  stop_loss_monitor.yml
Cron (4:30 PM ET)           →  daily_report.yml
```

→ [Full automation detail](docs/automation-cicd.md)

---

## The Tank

The paper brokerage. $10,000 starting bankroll, tracked in MongoDB. The Tank enforces:

- Whole shares only — `int(position_dollars / price)`, never fractional
- No broker API — execution is simulated, manual eTrade mirroring follows
- Full trade history with per-shark attribution, surfacing win rates per agent

Once The Tank demonstrates consistent edge over a meaningful sample size, real capital follows.

---

## Running Locally

```bash
# Prerequisites: uv, Python 3.12+, MongoDB URI + LLM API keys in environment

uv run python -m the_reef.main status    # portfolio state
uv run python -m the_reef.main scan      # run scanner once
uv run python -m the_reef.main dive NVDA # full 8-shark deep dive
uv run python -m the_reef.main sell NVDA # sell a position
uv run python -m the_reef.main report    # daily report + NAV snapshot
uv run python -m the_reef.main reset     # wipe and restart at $10,000
```

---

## Documentation

| | |
|---|---|
| [Architecture Overview](docs/architecture-overview.md) | Four-layer design, autonomy loop, technology choices, cost model |
| [AI Investment Committee](docs/ai-investment-committee.md) | Agent roster, panel scoring framework, position sizing, LLM routing |
| [Serverless Infrastructure](docs/serverless-infrastructure.md) | AWS stack, MongoDB Atlas, Terraform, IAM, cost breakdown |
| [Security Design](docs/security-design.md) | Secrets management, least privilege, transport security, blast radius |
| [Automation & CI/CD](docs/automation-cicd.md) | All 7 workflows, deploy rules, trading loop walkthrough |
| [Operations Runbook](docs/operations-runbook.md) | Day-to-day commands, failure recovery, MongoDB queries, health checks |
