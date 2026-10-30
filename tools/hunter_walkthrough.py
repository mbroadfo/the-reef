"""Regenerates docs/reef2-hunter-walkthrough.md from a real run of the engine on the synthetic scenario.

    uv run --frozen --no-sync python tools/hunter_walkthrough.py            # print
    uv run --frozen --no-sync python tools/hunter_walkthrough.py --write    # update the doc

Offline and deterministic: no network, no Atlas, no model. The numbers in the document are the
output of this script, not hand-written.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.fixtures.hunter_scenario import (  # noqa: E402
    EPOCH_ID, SLEEVE, START_INDEX, UNIVERSE, make_deps, make_world,
)
from the_reef.engine.advance import NoteKind, advance, bootstrap  # noqa: E402
from the_reef.ledger.events import EventKind  # noqa: E402
from the_reef.ledger.ledger import InMemoryEventStore, Ledger  # noqa: E402
from the_reef.ledger.state import replay  # noqa: E402
from the_reef.performance.metrics import (  # noqa: E402
    buy_and_hold, fund_nav_series, funded_capital, max_drawdown, round_trips, sleeve_nav_series, total_return,
)

D = Decimal
SESSIONS = 65


def pct(x: Decimal) -> str:
    return f"{x * 100:+.2f}%"


def money(x: Decimal) -> str:
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


def run_all():
    world = make_world()
    deps = make_deps(world)
    led = Ledger()
    bootstrap(led, deps, world.calendar.session(world.days[START_INDEX]).open - timedelta(hours=1))
    reports = [advance(led, deps, world.days[START_INDEX + i]) for i in range(SESSIONS)]
    return world, deps, led, reports


def event_line(e) -> str:
    d, p = e.draft, e.draft.payload
    t = d.occurred_at.strftime("%Y-%m-%d %H:%M UTC")
    k = d.kind
    if k is EventKind.ORDER_QUEUED:
        what = f"{p['intent']} up to {p['requested_shares']} {p['symbol']}, stop {p['stop_price']}, fill session {p['fill_session']}"
    elif k is EventKind.ORDER_REJECTED:
        what = f"{p['symbol']} {p['stage']} {p['code']}"
    elif k is EventKind.FILL:
        what = f"{p['side']} {p['shares']} {p['symbol']} @ {p['price']} (order {p['order_id']})"
    elif k is EventKind.STOP_UPDATED:
        what = f"{p['symbol']} stop -> {p['stop_price']}"
    else:
        what = ""
    return f"| {e.seq} | {t} | {k.value} | {what} |"


def balances(events, upto_day: str, sleeve: str, marks_day: str):
    """Books as of the close of ``upto_day`` (replay of every event up to that session's SESSION_CLOSED)."""
    cut = next(i for i, e in enumerate(events) if e.draft.kind is EventKind.SESSION_CLOSED
               and e.draft.payload["session_day"] == upto_day)
    st = replay(list(events[: cut + 1]))
    sl = st.epoch().sleeves[sleeve]
    mark = next(e.draft.payload for e in events if e.draft.kind is EventKind.SESSION_MARKED
                and e.draft.payload["session_day"] == marks_day)
    return st, sl, mark


STATUS = """## 6. What is real, what is simulated, what is missing

**Works and is tested** (the offline test suite): the calendar-aware gate, point-in-time instrument and corporate-action checks, quote validation, the deterministic Risk Engine, the event-sourced ledger with fund, sleeves, orders, valuation and session lifecycle, `advance(session)`, the Hunter rules, D0, gap-aware stops, performance and benchmark math, deterministic replay, and crash recovery at every append.

**Simulated**: all prices (synthetic bars), all fills (at the official open or a resting stop, no slippage or fees, no partial fills, daily bars so intraday ordering is approximated), the corporate-action and instrument data (static fixtures), and time (the loop is driven by a test harness, not a scheduler).

**Must exist before Reef 2.0 can be activated** (none of it is built):
1. Production point-in-time data adapters for bars, instruments and corporate actions, with a vendor decision and cost, that refuse queries they cannot answer point-in-time.
2. A MongoDB event-store adapter (unique indexes on `seq` and `event_id`) and an independently preserved ledger checkpoint, per the store contract in `the_reef/ledger/ledger.py`.
3. A configurable portfolio-wide aggregate stop-risk budget in the Risk Engine (today the budget is per position).
4. Sector data for the instrument master (unknown sectors are limited to 10% of NAV).
5. A scheduled runner for `advance`, wrapped in the release gates (a gated workflow, spend and kill-switch controls); nothing is scheduled today.
6. The remaining sharks as strategies on the same interface, and the D1-D3 shadow books on shared inputs.
7. Fees and slippage assumptions, dividends and splits, and a decision on average-cost versus lot accounting if tax lots matter.
8. The dashboard reading the ledger instead of the Reef 1.0 collections, and the Epoch 0 archive export.
9. An explicit activation approval.
"""


def main() -> str:
    world, deps, led, reports = run_all()
    events = list(led.store.read_all())
    hunter = deps.sleeves[0].strategy
    out: list[str] = []
    w = out.append

    w("# Reef 2.0: the Hunter vertical slice, end to end\n")
    w("Generated by `tools/hunter_walkthrough.py` from a real run of the engine. **Everything below is a simulation on "
      "synthetic prices** (`tests/fixtures/hunter_scenario.py`), built so each behaviour happens on a known day. It shows "
      "that the machinery works and is reproducible. It is not evidence that the strategy makes money.\n")
    w("## Setup\n")
    w(f"- Fund: $10,000, all cash, epoch `{EPOCH_ID}`. One sleeve, `{SLEEVE}`, funded by D0 with 40% = $4,000; $6,000 stays unallocated.")
    w(f"- Strategy: `{hunter.strategy_id}` v{hunter.version}, spec hash `{hunter.spec_hash}`. Rules are in the docstring of `the_reef/strategy/hunter.py`: "
      "20-session closing-high breakout, above the 50-session average, liquidity filter, stop at close minus 2 x ATR(14), trend-break exit below the 20-session average, stop only ever rises.")
    w("- Limits (unchanged): 10% per position, 0.5% of NAV at risk per position, 25% per sector (10% unknown), 60% invested, 2% daily-loss and 10% drawdown pauses.")
    w(f"- Universe: {', '.join(UNIVERSE)}. Sessions advanced: {SESSIONS} ({world.days[START_INDEX]} to {world.days[START_INDEX + SESSIONS - 1]}).")
    w("- Decisions at the close; fills at the next valid open; orders and fills are ledger events. No LLM, no Atlas, no network.\n")

    # --- the HUNT lifecycle
    w("## 1. One complete lifecycle: HUNT\n")
    hunt = [e for e in events if e.draft.payload.get("symbol") == "HUNT"
            and e.draft.kind in (EventKind.ORDER_QUEUED, EventKind.FILL, EventKind.STOP_UPDATED, EventKind.ORDER_REJECTED)]
    stops = [e for e in hunt if e.draft.kind is EventKind.STOP_UPDATED]
    shown = [e for e in hunt if e.draft.kind is not EventKind.STOP_UPDATED] + stops[:2] + stops[-1:]
    shown.sort(key=lambda e: e.seq)
    w("Ledger events (immutable, hash-chained; all but three of the stop raises omitted):\n")
    w("| seq | time | event | detail |\n|---|---|---|---|")
    for e in shown:
        w(event_line(e))
    w(f"\n{len(stops)} stop raises in total, each higher than the last.\n")
    queued = next(e for e in hunt if e.draft.kind is EventKind.ORDER_QUEUED).draft.payload
    entry = next(e for e in hunt if e.draft.kind is EventKind.FILL).draft.payload
    exit_ = [e for e in hunt if e.draft.kind is EventKind.FILL][-1].draft.payload
    note = next(n for r in reports for n in r.notes if n.kind is NoteKind.QUEUED and n.symbol == "HUNT")
    w("**Discovery and proposal** (close of 2026-08-28): " + note.detail + ".\n")
    w(f"**Gate and risk**: HUNT was tradable (listed, no pending corporate action, over 60 sessions of history). D0 capped the order at "
      f"{queued['requested_shares']} shares (sleeve cash split between the two best candidates); at the next open (2026-08-31) the Risk Engine sized it at the "
      f"official open price {entry['price']}: floor(10% x $10,000 / {entry['price']}) = {entry['shares']} shares, inside the 0.5% risk budget "
      f"(stop distance {Decimal(entry['price']) - Decimal(queued['stop_price'])}).\n")
    w("**Valuation** (sleeve books after each close):\n")
    w("| close of | sleeve cash | HUNT shares | stop | close mark | sleeve NAV | fund NAV |\n|---|---|---|---|---|---|---|")
    exit_day = exit_["session_day"]
    exit_prev = world.calendar.session(world.days[world.days.index(__import__("datetime").date.fromisoformat(exit_day)) - 1]).day.isoformat()
    for day in ("2026-08-28", entry["session_day"], "2026-09-25", exit_prev, exit_day):
        st, sl, mark = balances(events, day, SLEEVE, day)
        pos = sl.positions.get("HUNT")
        w(f"| {day} | {money(sl.cash)} | {pos.shares if pos else 0} | {pos.stop_price if pos else '-'} | "
          f"{mark['marks'].get('HUNT', '-')} | {money(D(mark['sleeve_nav'][SLEEVE]))} | {money(D(mark['nav']))} |")
    stop_gap = next(n for r in reports for n in r.notes if n.kind is NoteKind.STOP_GAP and n.symbol == "HUNT")
    w(f"\n**Exit** ({exit_day}): the resting stop was {stop_gap.detail.split('stop ')[1].split(',')[0]}. HUNT **opened at {exit_['price']}, far below it**, so the stop order "
      f"filled at the open price, not at the stop: the gap is paid. ({stop_gap.detail}.)\n")
    trip = next(t for t in round_trips(events, EPOCH_ID, SLEEVE) if t.symbol == "HUNT")
    w(f"**Financial outcome**: bought {trip.shares} at {trip.avg_entry}, sold at {trip.avg_exit}: realized P&L **{money(trip.pnl)}** "
      f"(exit reason: {trip.exit_reason}). Cash returned to the sleeve; the position left the books.\n")

    # --- other behaviours
    w("## 2. Passing and failing the checks\n")
    w("| day | symbol | what happened | where it was stopped |\n|---|---|---|---|")
    def first(kind, sym):
        return next(((r.session_day, n) for r in reports for n in r.notes if n.kind is kind and n.symbol == sym), None)
    for kind, sym, where in [
        (NoteKind.DECISION_REJECTED, "BIGP", "Risk Engine: one $1,500 share exceeds the 10% position cap on a $10,000 fund"),
        (NoteKind.DECISION_REJECTED, "DEAL", "Pre-trade gate: a definitive cash acquisition is pending (the SEM lesson)"),
        (NoteKind.FILL_REJECTED, "GAPR", "Fill gate: no official open print for the session, so nothing is bought at a stale price"),
        (NoteKind.QUEUED, "TRND", "Strategy exit (trend break) queued at the close, filled at the next open"),
    ]:
        item = first(kind, sym) if sym != "TRND" else next(((r.session_day, n) for r in reports for n in r.notes
                                                            if n.kind is kind and n.symbol == sym and n.detail.startswith("close")), None)
        if item:
            w(f"| {item[0]} | {sym} | {item[1].detail[:110]} | {where} |")
    w("")

    # --- all trades
    w("## 3. Every trade the sleeve made\n")
    w("| symbol | entry | exit | shares | avg entry | avg exit | P&L | exit |\n|---|---|---|---|---|---|---|---|")
    trips = round_trips(events, EPOCH_ID, SLEEVE)
    for t in trips:
        w(f"| {t.symbol} | {t.entry_day} | {t.exit_day} | {t.shares} | {t.avg_entry:.2f} | {t.avg_exit:.2f} | {money(t.pnl)} | {t.exit_reason} |")
    realized = led.state.epoch().sleeves[SLEEVE].realized_pnl
    w(f"\nClosed trades: {len(trips)}, total {money(sum((t.pnl for t in trips), D('0')))} = ledger realized P&L {money(realized)} "
      f"({sum(1 for t in trips if t.pnl > 0)} winners).\n")
    openpos = led.state.epoch().sleeves[SLEEVE].positions
    w("Open at the end: " + (", ".join(f"{s} x{p.shares} (stop {p.stop_price})" for s, p in sorted(openpos.items())) or "nothing") + ".\n")

    # --- performance
    w("## 4. Performance against buy-and-hold\n")
    funded = funded_capital(events, EPOCH_ID, SLEEVE)
    sl_series = sleeve_nav_series(events, EPOCH_ID, SLEEVE)
    fund_series = fund_nav_series(events, EPOCH_ID)
    bench = buy_and_hold(world.bars, world.calendar, UNIVERSE, funded, world.days[START_INDEX], world.days[START_INDEX + SESSIONS - 1])
    w("| | start | end | return | max drawdown |\n|---|---|---|---|---|")
    w(f"| Hunter sleeve (own capital base) | {money(funded)} | {money(sl_series[-1][1])} | {pct(total_return(sl_series, funded))} | {pct(max_drawdown(sl_series, funded))} |")
    w(f"| Fund (all $10,000) | $10,000.00 | {money(fund_series[-1][1])} | {pct(total_return(fund_series, D(10000)))} | {pct(max_drawdown(fund_series, D(10000)))} |")
    w(f"| Buy-and-hold, equal-dollar basket of the {len(UNIVERSE)} names, same {money(funded)}, whole shares | {money(funded)} | {money(bench.series[-1][1])} | "
      f"{pct(total_return(bench.series, funded))} | {pct(max_drawdown(bench.series, funded))} |")
    w("\nThe sleeve's return is against the $4,000 it was funded with, never against the whole fund. The benchmark is bought at the first session's open and marked at each close using only bars that had closed. "
      "With synthetic data and one scenario, the comparison shows the calculation works; it says nothing about edge.\n")

    # --- replay
    w("## 5. Deterministic replay and recovery\n")
    again = replay(events)
    cp = led.checkpoint()
    w(f"- Events in the ledger: {len(events)}; head hash `{led.state.head_hash[:16]}...`; state digest `{led.state.digest()[:16]}...`.")
    w(f"- Replaying every event from the start gives the same state digest: **{again.digest() == led.state.digest()}** and the same head hash: **{again.head_hash == led.state.head_hash}**.")
    world2 = make_world(); deps2 = make_deps(world2)
    led2 = Ledger(); bootstrap(led2, deps2, world2.calendar.session(world2.days[START_INDEX]).open - timedelta(hours=1))
    for i in range(SESSIONS):
        advance(led2, deps2, world2.days[START_INDEX + i])
    w(f"- A second, independent run of the whole simulation produces an identical ledger (same head hash): **{led2.state.head_hash == led.state.head_hash}**.")
    ok = Ledger(InMemoryEventStore(events), expected=cp)
    w(f"- Loading the stored events against the preserved checkpoint (seq {cp.seq}) succeeds: **{ok.state.digest() == led.state.digest()}**.")
    w("- Crash recovery: the test suite kills the process at every single append of a 25-session run (over 100 crash points), reloads from what the store durably holds, resumes with `next_session_to_advance`, and requires the final state to equal the uninterrupted run exactly (`tests/hunter/test_engine_safety.py`).\n")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    text = main()
    if "--write" in sys.argv:
        (ROOT / "docs" / "reef2-hunter-walkthrough.md").write_text(text, encoding="utf-8")
        print("written")
    else:
        print(text)
