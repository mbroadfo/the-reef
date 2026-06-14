# The Reef — AI Investment Committee

## Overview

The investment committee is an 8-agent CrewAI pipeline. Each agent is a specialist with a defined role, a specific LLM, and a constrained tool set. Agents execute sequentially, each reading the full output of all prior agents before producing their own analysis.

The pipeline ends with Apex Shark, who has sole trade authority. No other agent can execute a buy or sell.

---

## Agent Roster

| Agent | LLM | Role | Tools |
|---|---|---|---|
| Hunter Shark | GPT-4o-mini | Technical signal validation — breakouts, volume spikes | Price, History, Serper |
| Research Shark | GPT-4o | Fundamentals, earnings, valuation | Price, History, Serper |
| Macro Shark | GPT-4o | Sector flows, rates, VIX, macro regime | Serper |
| Sentiment Shark | GPT-4o | News narrative, social momentum, positioning | Serper |
| Contrarian Shark | Claude Sonnet 4.6 | Bear thesis, adversarial challenge | Serper |
| Risk Shark | Claude Sonnet 4.6 | Portfolio heat, concentration, stop audit | Portfolio |
| Wildcard Shark | GPT-4o | Crypto-correlated, special situations, outlier thesis | Price, History, Serper |
| Apex Shark | Claude Sonnet 4.6 | Portfolio Manager — panel scoring, sizing, final execution | Portfolio, Buy, Sell, StopLoss, SharkHistory |

---

## Signal Routing

The scanner produces typed signals. The crew routes the first task (Hunter Research) to a specialist based on signal type — no hardcoded agent in tasks.yaml for this task.

```python
VOLUME_SPIKE       → Hunter Shark
PRICE_BREAKOUT     → Hunter Shark
EARNINGS_UPCOMING  → Research Shark
NEWS_SENTIMENT     → Sentiment Shark
PRICE_DROP         → Contrarian Shark
RSI_OVERSOLD       → Contrarian Shark
RSI_OVERBOUGHT     → Contrarian Shark
default            → Hunter Shark
```

Macro Shark, Wildcard Shark, and Sentiment Shark can make **unsolicited nominations** — proposing tickers not in the original signal. These appear in their task output but have no automatic action path today.

---

## Task Pipeline (Sequential)

```
1. hunter_research       ← signal_type routed agent; validates the technical setup
2. research_analysis     ← fundamentals, valuation, earnings calendar
3. macro_analysis        ← sector/macro regime; GO / CAUTION / AVOID verdict
4. sentiment_analysis    ← news narrative; BULLISH / NEUTRAL / BEARISH verdict
5. contrarian_challenge  ← steelman bear case; worry score 1–10
6. risk_assessment       ← portfolio heat score 1–10; concentration; stop audit
7. wildcard_nomination   ← special situation lens; crypto correlation; outlier
8. apex_decision         ← reads all 7 outputs; panel score; sizing; BUY/HOLD/PASS
```

Each task declares `context:` on all prior tasks. Apex reads the complete committee record before deciding.

---

## Panel Scoring Framework (0–9)

Apex synthesizes committee output into a single panel score before sizing.

### Base Score Components

| Source | Output | Score |
|---|---|---|
| Hunter Shark | HIGH conviction | +3 |
| Hunter Shark | MEDIUM conviction | +2 |
| Hunter Shark | LOW conviction | +1 |
| Research Shark | CHEAP (undervalued) | +3 |
| Research Shark | FAIR value | +2 |
| Research Shark | EXPENSIVE | +0 |
| Macro Shark | GO | +3 |
| Macro Shark | CAUTION | +1 |
| Macro Shark | AVOID | +0 |

**Base score range: 0–9**

### Contrarian Modifier

| Contrarian Worry Score | Panel Adjustment |
|---|---|
| 1–4 (low concern) | 0 |
| 5–6 (moderate) | −1 |
| 7–8 (elevated) | −2 |
| 9–10 (severe) | −3 |

---

## Position Sizing

Sizing is computed by Apex after applying all modifiers. Whole shares only — `int(position_dollars / price)`.

### Base Size by Panel Score

| Panel Score | Base Position Size |
|---|---|
| 7–9 | Full position |
| 5–6 | 75% |
| 3–4 | 50% |
| 1–2 | 25% |
| 0 | PASS (no trade) |

### Risk Modifiers (applied after base)

| Condition | Adjustment |
|---|---|
| Risk heat score 7–8 | −25% |
| Risk heat score 9–10 | −50% |
| Contrarian worry 9–10 | Additional −25% |

### Example

Panel score 6 + Risk heat 7 + Contrarian worry 9:
- Base: 75%
- Risk heat 7: −25% → 50%
- Contrarian worry 9: −25% → 37.5% → rounded to nearest valid size

---

## Apex Authority Model

- Apex is the **only** agent with `ExecuteBuyTool` and `ExecuteSellTool`
- Contrarian Shark and Risk Shark produce scores — they have **no veto power** (this is explicit in their agent backstory)
- Macro and Sentiment produce verdicts that feed the panel score but cannot block a trade
- `GetSharkHistoryTool` lets Apex consult historical win rates by hunter before sizing up

---

## CrewAI Implementation Notes

- `@CrewBase` decorator — **no `super().__init__()`** — breaks MRO; use `set_tank()` before instantiation
- `hunter_research` task has no `agent:` field in tasks.yaml — dynamically assigned via `select_hunter(signal_type)` in crew.py
- All agents defined with `@agent` decorator, all tasks with `@task`, crew assembled with `@crew`
- LLM field in agents.yaml maps directly to litellm provider strings

---

## Signal Types & Priority

| Signal | Priority | Typical Source Agent |
|---|---|---|
| EARNINGS_UPCOMING | 10 | Research Shark |
| VOLUME_SPIKE | 9 | Hunter Shark |
| PRICE_BREAKOUT | 8 | Hunter Shark |
| NEWS_SENTIMENT | 8 | Sentiment Shark |
| PRICE_DROP | 7 | Contrarian Shark |
| RSI_OVERSOLD | 6 | Contrarian Shark |
| RSI_OVERBOUGHT | 5 | Contrarian Shark |

Scanner thresholds: EARNINGS_UPCOMING within 14 days; NEWS_SENTIMENT fires when 5-day change >5% but today's move <2% (lagging narrative).
