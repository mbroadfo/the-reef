"""Performance measured from the ledger alone, plus a buy-and-hold benchmark.

Everything is derived from replayable events, so the same ledger always gives the same numbers.
Sleeve performance is the sleeve's own NAV against the capital it was funded with; fund
performance is the fund NAV against the epoch's initial cash. Neither is a percentage of an
unrelated base (the Reef 1.0 attribution defect).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from the_reef.ledger.events import EventKind, LedgerEvent
from the_reef.market.bars import BarSource
from the_reef.market.calendar import MarketCalendar

D = Decimal


@dataclass(frozen=True)
class RoundTrip:
    sleeve_id: str
    symbol: str
    entry_day: str
    exit_day: str
    shares: int
    avg_entry: Decimal
    avg_exit: Decimal
    pnl: Decimal
    exit_reason: str


def sleeve_nav_series(events: Sequence[LedgerEvent], epoch_id: str, sleeve_id: str) -> list[tuple[str, Decimal]]:
    out = []
    for e in events:
        d = e.draft
        if d.epoch_id == epoch_id and d.kind is EventKind.SESSION_MARKED:
            out.append((str(d.payload["session_day"]), D(str(d.payload["sleeve_nav"][sleeve_id]))))
    return out


def fund_nav_series(events: Sequence[LedgerEvent], epoch_id: str) -> list[tuple[str, Decimal]]:
    return [(str(e.draft.payload["session_day"]), D(str(e.draft.payload["nav"])))
            for e in events if e.draft.epoch_id == epoch_id and e.draft.kind is EventKind.SESSION_MARKED]


def funded_capital(events: Sequence[LedgerEvent], epoch_id: str, sleeve_id: str) -> Decimal:
    return sum((D(str(e.draft.payload["amount"])) for e in events
                if e.draft.epoch_id == epoch_id and e.draft.kind is EventKind.SLEEVE_FUNDED
                and e.draft.payload["sleeve_id"] == sleeve_id), D("0"))


def round_trips(events: Sequence[LedgerEvent], epoch_id: str, sleeve_id: str) -> list[RoundTrip]:
    open_: dict[str, dict] = {}
    out: list[RoundTrip] = []
    for e in events:
        d = e.draft
        if d.epoch_id != epoch_id or d.kind is not EventKind.FILL or d.payload["sleeve_id"] != sleeve_id:
            continue
        p = d.payload
        sym, shares, price, day = str(p["symbol"]), int(p["shares"]), D(str(p["price"])), str(p["session_day"])
        if p["side"] == "BUY":
            t = open_.setdefault(sym, {"entry_day": day, "shares": 0, "cost": D("0"), "proceeds": D("0"), "sold": 0})
            t["shares"] += shares
            t["cost"] += price * shares
        else:
            t = open_[sym]
            t["proceeds"] += price * shares
            t["sold"] += shares
            t["held"] = t["shares"] - t["sold"]
            if t["sold"] == t["shares"]:
                reason = "stop" if str(p["order_id"]).startswith("stop:") else "strategy exit"
                avg_cost = t["cost"] / t["shares"]
                out.append(RoundTrip(sleeve_id, sym, t["entry_day"], day, t["shares"], avg_cost,
                                     t["proceeds"] / t["sold"], t["proceeds"] - t["cost"], reason))
                del open_[sym]
    return out


@dataclass(frozen=True)
class FlowPoint:
    """One marked session of a sleeve, with the capital that was in it at the start of that session.

    ``base`` is the previous mark plus any transfers made since (a transfer is decided after the close, so it
    belongs to the next session). ``ret`` = nav / base - 1 therefore measures only what the sleeve earned;
    ``index`` chains those returns (time-weighted), starting at 1.
    """
    day: str
    nav: Decimal
    base: Decimal
    flow: Decimal  # net transfers into the sleeve since the previous mark (the first mark carries the initial funding)
    ret: Decimal
    index: Decimal


_INDEX_QUANT = D("0.0000000001")


def flow_adjusted_series(events: Sequence[LedgerEvent], epoch_id: str, sleeve_id: str, through_seq: int | None = None) -> list[FlowPoint]:
    """Capital-flow-adjusted (time-weighted) performance of a sleeve, from ledger events only.

    Receiving $500 raises ``nav`` and ``base`` together, so it never shows up as a return."""
    out: list[FlowPoint] = []
    pending = D("0")
    prev_nav = D("0")
    index = D("1")
    for e in events:
        if through_seq is not None and e.seq > through_seq:
            break
        d = e.draft
        if d.epoch_id != epoch_id:
            continue
        if d.kind is EventKind.SLEEVE_FUNDED and d.payload["sleeve_id"] == sleeve_id:
            pending += D(str(d.payload["amount"]))
        elif d.kind is EventKind.SESSION_MARKED and sleeve_id in d.payload["sleeve_nav"]:
            nav = D(str(d.payload["sleeve_nav"][sleeve_id]))
            base = prev_nav + pending
            ret = (nav / base - 1) if base > 0 else D("0")
            index = (index * (1 + ret)).quantize(_INDEX_QUANT)
            out.append(FlowPoint(str(d.payload["session_day"]), nav, base, pending, ret, index))
            prev_nav, pending = nav, D("0")
    return out


def window_performance(points: Sequence[FlowPoint], lookback: int) -> tuple[Decimal, Decimal, int]:
    """(return, max drawdown <= 0, sessions) over the last ``lookback`` flow-adjusted sessions."""
    win = list(points[-lookback:]) if lookback > 0 else list(points)
    if not win:
        return D("0"), D("0"), 0
    start = D("1")
    prior = points[: len(points) - len(win)]
    if prior:
        start = prior[-1].index
    peak, worst = start, D("0")
    for p in win:
        peak = max(peak, p.index)
        worst = min(worst, p.index / peak - 1)
    return win[-1].index / start - 1, worst, len(win)


def total_return(series: Sequence[tuple[str, Decimal]], base: Decimal) -> Decimal:
    return (series[-1][1] / base - 1) if series and base > 0 else D("0")


def max_drawdown(series: Sequence[tuple[str, Decimal]], base: Decimal) -> Decimal:
    peak, worst = base, D("0")
    for _, v in series:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


@dataclass(frozen=True)
class Benchmark:
    series: list[tuple[str, Decimal]]
    shares: dict[str, int]
    cash: Decimal


def buy_and_hold(
    source: BarSource, calendar: MarketCalendar, symbols: Sequence[str], capital: Decimal, start: date, end: date,
) -> Benchmark:
    """Equal-dollar basket bought at the first session's open (whole shares), held to ``end``.

    Marked at each session's close. Uses only bars of sessions that have closed by each mark.
    """
    first = calendar.session(start)
    assert first is not None
    shares: dict[str, int] = {}
    cash = capital
    per = capital / len(symbols)
    for s in symbols:
        q = source.official_open(s, first)
        if q is None or q.price is None:
            shares[s] = 0
            continue
        n = int(per / q.price)
        shares[s] = n
        cash -= n * q.price
    series: list[tuple[str, Decimal]] = []
    day = start
    while day <= end:
        sess = calendar.session(day)
        if sess is not None:
            nav = cash
            for s, n in shares.items():
                bar = source.bar(s, day, sess.close)
                if bar is not None:
                    nav += n * bar.close
            series.append((day.isoformat(), nav))
        day = date.fromordinal(day.toordinal() + 1)
    return Benchmark(series, shares, cash)
