# Reef 2.0 aquarium MVP: a competing-pods vertical slice

Run it: `uv run python tools/aquarium_demo.py`, then open http://localhost:5173/. (Or build the snapshot with
`uv run python tools/build_competition_snapshot.py` and `npm run dev` in `dashboard/frontend`.)

**What it is.** A deterministic, fixture-driven competition run through the real Reef 2.0 engine and ledger, rendered by the
existing React app. Prices are synthetic and say so on every page. Nothing is live, no money, no Atlas, no LLM, no cost.

## What was built
| Piece | Where |
|---|---|
| Six registered pods, honest ACTIVE/INACTIVE status, mandates | `the_reef/pods/registry.py` |
| Research-agent interface and deterministic agents (LLM agents can implement the same `analyze`) | `the_reef/pods/research.py`, `strategy/base.py::Finding` |
| Shared proposal contract (ticker, thesis, evidence, timestamps, entry/exit plan, risk, capital request) | `the_reef/pods/contract.py` |
| Second strategy, Contrarian (mean reversion), competing with Momentum (Hunter, unmodified) | `the_reef/strategy/contrarian.py` |
| Ledger records of what Apex was shown and decided: `PROPOSAL_SUBMITTED`, `APEX_DECISION` (audit only, move no money) | `ledger/events.py`, `engine/advance.py::_decide` |
| Signals withheld before ranking because the gate would refuse the name: `OPPORTUNITY_SUPPRESSED` (audit only; not proposals) | `engine/advance.py::_screen_candidates`, [selection](reef2-selection.md) |
| Apex = deterministic D0: fixed sleeve weights, best-ranked idea per pod per session, never more than asked, then gate and Risk Engine | `allocation/d0.py` + `engine/advance.py` |
| Engine-to-UI contract: one JSON snapshot derived from the ledger only, with the raw events | `the_reef/aquarium/snapshot.py`, `public/reef2/snapshot.json` |
| Aquarium, team pages, proposal story, Research Lab | `dashboard/frontend/src/reef2/` |

## Reading the demo
Aquarium: six pods (two hunting, four asleep with the reason), a return race, Apex's desk of every pitch, a risk-adjusted scoreboard.
Click a pitch for the story: research, pitch, Apex's rule trace (rank, capital, gate, risk), fill, price path with stop, and who benefited
(position, sleeve before/after, whole fund). Declined pitches show the rule that stopped them and a clearly hypothetical price note.
The Research Lab re-verifies the hash chain and recomputes each sleeve's books in the browser from raw events, shows formulas, and has a ledger explorer.

## Honest limits
- Synthetic prices from a seeded generator (`tests/fixtures/competition_scenario.py`); 70 sessions; two active pods. Rankings demonstrate accounting, not skill.
- Inactive pods (Value, Macro, Earnings, News) have no strategy, sleeve or numbers. Their reasons are shown, not hidden.
- Not yet built: live or cached real-data feed into the aquarium, MongoDB event store, scheduled runner, portfolio-wide stop-risk budget,
  fees/slippage in this demo, an Apex that uses judgment (D1-D3 shadow books), LLM research agents under the shared $2/day cap.
- Changes to the shared engine: two audit events, and the capital a pod asks for caps what D0 grants (bare strategies ask for all their cash, so Hunter is unchanged).

## Ideas adopted (no code copied)
- [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund): distinct investor-style agents with different philosophies feeding a portfolio-manager step, with a risk step alongside.
- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents): role-specialised research (technical, market structure, risk) producing a reasoned proposal that a trader and independent risk check act on.
- [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot): a layered agent platform that keeps data, analysis and decision layers separate, which is the shape of the snapshot contract here.
