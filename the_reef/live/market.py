"""Real daily market data for the live-paper epoch: incremental refresh, vetting, holds and completeness.

The live cache is a private copy of the research cache (``seed``) that only ever grows. ``refresh`` appends a bar
only after it passes every check below; a bar that fails is *not stored* (it goes to ``ingest.jsonl`` with its
reason), so the engine meets the gap the same way it would meet a missing print: unmarked book, no fill. Nothing here
repairs, interpolates or carries a price forward.

A bar is stored only if
  * its day is an exchange session and that session closed at least ``FINALIZE_DELAY`` before ``now``
    (a partial, same-day or future row is never a bar);
  * its OHLC is consistent and its volume is positive;
  * it is not a split day (a split re-bases the vendor's whole history; the symbol is put on hold instead), and
  * it does not jump more than ``MAX_CLOSE_JUMP`` from the previous close unless the symbol is held (a held name
    keeps its real moves, since its stop must see them; the jump is flagged for review instead).
Rows already stored are never overwritten. If a re-fetch disagrees with a stored bar (the vendor restated history)
the symbol is put on hold and the disagreement is logged.

Holds are append-only records in ``holds.jsonl``. A held symbol is reported as HALTED by the instrument master, so
the existing tradability gate stops new entries and the engine suppresses its signals with an audit record.
All of it is derived from files that only grow, so replaying a session after a restart sees the same facts.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence

from the_reef.backtest import cache
from the_reef.backtest.history import HistoricalBarSource
from the_reef.backtest.universe import BENCHMARK, SECTOR_OF
from the_reef.live.config import PROVIDER
from the_reef.live.store import atomic_write
from the_reef.market.bars import DailyBar
from the_reef.market.calendar import CalendarRangeError, MarketCalendar, NEW_YORK, Session
from the_reef.market.instruments import InstrumentRecord, InstrumentStatus
from the_reef.market.quotes import Quote

D = Decimal
FINALIZE_DELAY = timedelta(minutes=30)  # a session's bar is final no sooner than this after the close
CRITICAL_GRACE = timedelta(hours=3)  # how long to wait for a held/ordered symbol's bar before the engine fails closed on it
MIN_COVERAGE = D("0.95")  # share of the universe that must have a bar for a session to be processed
MAX_CLOSE_JUMP = D("0.40")
HALT_SESSIONS = 3  # consecutive sessions with no bar (while the benchmark has one) before a name is treated as halted
RESTATE_TOLERANCE = D("0.0005")  # relative; vendors re-round, they do not move a close by 5 bp

INGEST = "ingest.jsonl"
HOLDS = "holds.jsonl"


def _now_iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat()


def finalized_at(session: Session) -> datetime:
    return session.close + FINALIZE_DELAY


def latest_finalized_session(calendar: MarketCalendar, now: datetime) -> Session | None:
    """The newest session whose bar may be final at ``now``."""
    d = now.astimezone(NEW_YORK).date()
    for _ in range(14):
        try:
            s = calendar.session(d)
        except CalendarRangeError:
            return None
        if s is not None and finalized_at(s) <= now:
            return s
        d -= timedelta(days=1)
    return None


# --- fetching --------------------------------------------------------------------------------------------------

class DailyFetcher(Protocol):
    name: str

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> Mapping[str, list[cache.RawRow]]:
        """Daily rows with ``start <= day < end`` per symbol (symbols with nothing may be absent)."""
        ...


class YahooFetcher:
    """The one network adapter. Free, no key; needs the ``data`` dependency group (``uv run --group data``)."""

    name = "yfinance"

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> Mapping[str, list[cache.RawRow]]:
        import yfinance as yf  # noqa: PLC0415

        frame = yf.download(list(symbols), start=start.isoformat(), end=end.isoformat(), auto_adjust=False, actions=True,
                            group_by="ticker", progress=False, threads=True)
        out: dict[str, list[cache.RawRow]] = {}
        for sym in symbols:
            try:
                df = frame[sym].dropna(subset=["Open", "High", "Low", "Close"])
            except KeyError:
                continue
            out[sym] = [cache.RawRow(
                idx.date(), D(str(r["Open"])), D(str(r["High"])), D(str(r["Low"])), D(str(r["Close"])), D(str(r["Adj Close"])),
                int(r["Volume"] or 0), D(str(r.get("Dividends", 0) or 0)), D(str(r.get("Stock Splits", 0) or 0)),
            ) for idx, r in df.iterrows()]
        return out


# --- cache files -----------------------------------------------------------------------------------------------

def _csv_text(rows: Iterable[cache.RawRow]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cache.FIELDS)
    for r in rows:
        w.writerow([r.day.isoformat(), r.open, r.high, r.low, r.close, r.adj_close, r.volume, r.dividend, r.split])
    return buf.getvalue()


def _row_sha(r: cache.RawRow) -> str:
    return hashlib.sha256(f"{r.day}|{r.open}|{r.high}|{r.low}|{r.close}|{r.volume}".encode()).hexdigest()[:16]


def _log(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()


def read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


@dataclass(frozen=True)
class Hold:
    symbol: str
    kind: str  # SPLIT | RESTATED | SUSPECT_JUMP
    effective_from: datetime
    detail: str


def read_holds(market_dir: Path) -> list[Hold]:
    return [Hold(h["symbol"], h["kind"], datetime.fromisoformat(h["effective_from"]), h["detail"]) for h in read_log(market_dir / HOLDS)]


def _add_hold(market_dir: Path, hold: Hold, recorded: datetime, report: "RefreshReport") -> None:
    if any(h.symbol == hold.symbol and h.kind == hold.kind for h in read_holds(market_dir)):
        return
    _log(market_dir / HOLDS, {"symbol": hold.symbol, "kind": hold.kind, "effective_from": hold.effective_from.astimezone(timezone.utc).isoformat(),
                              "detail": hold.detail, "recorded_at": _now_iso(recorded)})
    report.holds_added.append(f"{hold.symbol} {hold.kind}")


@dataclass
class RefreshReport:
    started: str = ""
    symbols: int = 0
    appended: dict[str, int] = field(default_factory=dict)
    quarantined: list[str] = field(default_factory=list)
    flagged: list[str] = field(default_factory=list)
    holds_added: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return sum(self.appended.values())


def refresh(market_dir: Path, symbols: Sequence[str], fetcher: DailyFetcher, calendar: MarketCalendar, now: datetime,
            *, held: frozenset[str] = frozenset(), overlap_days: int = 10) -> RefreshReport:
    """Append every newly final, valid daily bar. Idempotent: running it twice appends nothing the second time."""
    rep = RefreshReport(started=_now_iso(now), symbols=len(symbols))
    horizon = latest_finalized_session(calendar, now)
    if horizon is None:
        rep.errors.append("no finalized session at this time (calendar edge?)")
        return rep
    stored = {s: cache.read(s, market_dir) for s in symbols}
    empty = [s for s, rows in stored.items() if not rows]
    for s in empty:
        rep.errors.append(f"{s}: no warmup history in the live cache (run seed first)")
    todo = [s for s in symbols if s not in empty]
    if not todo:
        return rep
    start = min(stored[s][-1].day for s in todo) - timedelta(days=overlap_days)
    try:
        fetched = fetcher.fetch(todo, start, horizon.day + timedelta(days=1))
    except Exception as exc:  # noqa: BLE001 - a network failure must not look like "no new data"
        rep.errors.append(f"fetch failed: {type(exc).__name__}: {exc}")
        return rep
    ingest = market_dir / INGEST
    seen_quarantine = {(r["symbol"], r["day"], r["reason"]) for r in read_log(ingest) if r["event"] in ("QUARANTINED", "RESTATED")}

    def note(event: str, sym: str, day: date, reason: str, detail: str = "") -> None:
        _log(ingest, {"at": _now_iso(now), "event": event, "symbol": sym, "day": day.isoformat(), "reason": reason, "detail": detail})

    for sym in todo:
        have = {r.day: r for r in stored[sym]}
        last = stored[sym][-1]
        prev_close, prev_day = last.close, last.day
        added: list[cache.RawRow] = []
        for r in sorted(fetched.get(sym, []), key=lambda r: r.day):
            old = have.get(r.day)
            if old is not None:
                for a, b, nm in ((old.open, r.open, "open"), (old.high, r.high, "high"), (old.low, r.low, "low"), (old.close, r.close, "close")):
                    if abs(b - a) > a * RESTATE_TOLERANCE:
                        key = (sym, r.day.isoformat(), "RESTATED")
                        if key not in seen_quarantine:
                            seen_quarantine.add(key)
                            note("RESTATED", sym, r.day, "RESTATED", f"{nm}: stored {a}, vendor now {b}")
                            rep.quarantined.append(f"{sym} {r.day} RESTATED")
                        eff = calendar.session(r.day).close  # type: ignore[union-attr]  # in force from the disputed bar's own close
                        _add_hold(market_dir, Hold(sym, "RESTATED", eff, f"vendor history for {r.day} changed ({nm} {a} -> {b})"), now, rep)
                        break
                continue
            if r.day < prev_day:
                continue  # a late backfill inside stored history: never inserted, the strategies already decided without it
            reason = None
            session = None
            try:
                session = calendar.session(r.day)
            except CalendarRangeError:
                pass
            if session is None:
                reason = "NOT_A_SESSION"
            elif finalized_at(session) > now or r.day > horizon.day:
                reason = "NOT_FINAL"
            elif r.split not in (0, 1):
                reason = "SPLIT"
            else:
                try:
                    DailyBar(sym, r.day, r.open, r.high, r.low, r.close, r.volume, "check")
                except ValueError:
                    reason = "BAD_OHLC"
                if reason is None and r.volume <= 0:
                    reason = "ZERO_VOLUME"
            if reason is None and abs(r.close / prev_close - 1) > MAX_CLOSE_JUMP:
                if sym in held:
                    rep.flagged.append(f"{sym} {r.day} moved {(r.close / prev_close - 1) * 100:+.1f}% (held: stored, review)")
                    note("FLAG", sym, r.day, "LARGE_MOVE", f"close {prev_close} -> {r.close}")
                else:
                    reason = "SUSPECT_JUMP"
            if reason is not None:
                key = (sym, r.day.isoformat(), reason)
                if reason != "NOT_FINAL" and key not in seen_quarantine:  # a not-yet-final row is simply fetched again later
                    seen_quarantine.add(key)
                    note("QUARANTINED", sym, r.day, reason, f"o={r.open} h={r.high} l={r.low} c={r.close} v={r.volume} split={r.split}")
                    rep.quarantined.append(f"{sym} {r.day} {reason}")
                if reason in ("SPLIT", "SUSPECT_JUMP") and session is not None:
                    _add_hold(market_dir, Hold(sym, reason, session.close, f"{r.day}: {reason.lower().replace('_', ' ')}"), now, rep)
                if reason in ("SPLIT", "SUSPECT_JUMP"):
                    break  # nothing after a re-basing or implausible bar is stored until a human decides
                continue
            if r.day > prev_day + timedelta(days=1):
                gap = calendar.session_count(prev_day + timedelta(days=1), r.day - timedelta(days=1)) if r.day - prev_day > timedelta(days=1) else 0
                if gap:
                    note("GAP", sym, r.day, "MISSING_SESSIONS", f"{gap} session(s) after {prev_day}")
            added.append(r)
            prev_close, prev_day = r.close, r.day
            note("ADDED", sym, r.day, "OK", _row_sha(r))
            if r.dividend > 0:
                note("DIVIDEND", sym, r.day, "EX_DIVIDEND", f"{r.dividend} per share")
        if added:
            atomic_write(cache.path_for(sym, market_dir), _csv_text([*stored[sym], *added]))
            rep.appended[sym] = len(added)
    if rep.rows:
        cache.write_manifest(cache.build_manifest(list(symbols), {
            "provider": PROVIDER, "refreshed_at": _now_iso(now), "note": "live-paper cache: seeded copy plus vetted incremental rows"}, market_dir), market_dir)
    return rep


def seed(market_dir: Path, source_dir: Path, symbols: Sequence[str], before: date) -> dict[str, int]:
    """Copy warmup history (rows strictly before ``before``) from the research cache. Never copies a row the live
    epoch could decide on, so nothing enters without passing ``refresh``."""
    out: dict[str, int] = {}
    for sym in symbols:
        rows = [r for r in cache.read(sym, source_dir) if r.day < before]
        if rows:
            atomic_write(cache.path_for(sym, market_dir), _csv_text(rows))
            out[sym] = len(rows)
    if out:
        src = cache.verify_manifest(source_dir)
        cache.write_manifest(cache.build_manifest(list(symbols), {
            "provider": PROVIDER, "seeded_from_manifest_digest": src.digest, "seeded_rows_before": before.isoformat(),
            "note": "warmup history copied from the research cache; no live row is in the seed"}, market_dir), market_dir)
    return out


# --- what the engine sees --------------------------------------------------------------------------------------

class VettedBars:
    """``BarSource`` over the live cache that also refuses anything past the finalized horizon."""

    def __init__(self, inner: HistoricalBarSource, horizon: date) -> None:
        self._inner, self.horizon = inner, horizon

    def history(self, symbol: str, as_of: datetime, limit: int | None = None) -> Sequence[DailyBar]:
        return tuple(b for b in self._inner.history(symbol, as_of, limit) if b.day <= self.horizon)

    def bar(self, symbol: str, day: date, as_of: datetime) -> DailyBar | None:
        return self._inner.bar(symbol, day, as_of) if day <= self.horizon else None

    def official_open(self, symbol: str, session: Session) -> Quote | None:
        return self._inner.official_open(symbol, session) if session.day <= self.horizon else None

    def official_close(self, symbol: str, session: Session) -> Quote | None:
        return self._inner.official_close(symbol, session) if session.day <= self.horizon else None

    def __getattr__(self, name: str):  # symbols(), quality, days(): read-only extras of the inner source
        return getattr(self._inner, name)


class LiveInstrumentMaster:
    """Point-in-time instrument facts for the live universe. Every symbol is ACTIVE unless a hold applies at ``as_of``:
    a recorded SPLIT / RESTATED / SUSPECT_JUMP hold, or ``HALT_SESSIONS`` consecutive sessions with no bar while the
    benchmark traded. A held symbol is HALTED, which blocks every intent in the existing gate."""

    def __init__(self, bars: HistoricalBarSource, calendar: MarketCalendar, market_dir: Path) -> None:
        self._bars, self._cal = bars, calendar
        self._holds: dict[str, list[Hold]] = {}
        for h in read_holds(market_dir):
            self._holds.setdefault(h.symbol, []).append(h)
        self._bench = bars.days(BENCHMARK)
        self._have = {s: set(bars.days(s)) for s in bars.symbols()}
        self._memo: dict[tuple[str, date], int] = {}

    def holds_for(self, symbol: str, as_of: datetime) -> list[Hold]:
        return [h for h in self._holds.get(symbol, ()) if h.effective_from <= as_of]

    def silent_sessions(self, symbol: str, as_of: datetime) -> int:
        """Consecutive most-recent sessions closed by ``as_of`` on which the benchmark has a bar and ``symbol`` has none."""
        closed = [d for d in self._bench if self._cal.session(d).close <= as_of]  # type: ignore[union-attr]
        if not closed:
            return 0
        key = (symbol, closed[-1])
        if key not in self._memo:
            have, n = self._have.get(symbol, set()), 0
            for d in reversed(closed):
                if d in have:
                    break
                n += 1
            self._memo[key] = n
        return self._memo[key]

    def reasons(self, symbol: str, as_of: datetime) -> list[str]:
        out = [f"{h.kind}: {h.detail}" for h in self.holds_for(symbol, as_of)]
        n = self.silent_sessions(symbol, as_of)
        if n >= HALT_SESSIONS:
            out.append(f"NO_DATA: no bar for the last {n} sessions while the benchmark traded")
        return out

    def get(self, symbol: str, as_of: datetime) -> InstrumentRecord | None:
        days = self._bars.days(symbol)
        if not days:
            return None
        why = self.reasons(symbol, as_of)
        status = InstrumentStatus.HALTED if why else InstrumentStatus.ACTIVE
        return InstrumentRecord(symbol, "NYSE", status, days[0], None, SECTOR_OF.get(symbol),
                                "live-cache" + (": " + "; ".join(why) if why else ""), datetime(2000, 1, 1, tzinfo=timezone.utc))


# --- is the session ready to process? -------------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionAssessment:
    day: date
    state: str  # READY | WAIT_DATA | WAIT_CRITICAL
    covered: int
    universe: int
    benchmark: bool
    missing: tuple[str, ...]
    critical_missing: tuple[str, ...]
    digest: str
    reasons: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.state == "READY"


def session_digest(bars: HistoricalBarSource, symbols: Sequence[str], day: date) -> str:
    """Fingerprint of the bars the engine will see for ``day``; the ledger records it so later tampering is detectable."""
    h = hashlib.sha256()
    far = datetime(2100, 1, 1, tzinfo=timezone.utc)
    for s in sorted(symbols):
        b = bars.bar(s, day, far)
        if b is not None:
            h.update(f"{s}|{b.day}|{b.open}|{b.high}|{b.low}|{b.close}|{b.volume}\n".encode())
    return h.hexdigest()


def assess_session(bars: HistoricalBarSource, calendar: MarketCalendar, day: date, universe: Sequence[str],
                   critical: Iterable[str], now: datetime) -> SessionAssessment:
    """May session ``day`` be processed with the data on disk at ``now``? Fails closed: a missing benchmark or thin
    coverage always waits; a missing held/ordered symbol waits ``CRITICAL_GRACE``, after which the engine fails
    closed on that symbol (unmarked, order refused) rather than the whole fund stalling forever."""
    session = calendar.session(day)
    assert session is not None
    days = {s: set(bars.days(s)) for s in [*universe, BENCHMARK]}
    have = lambda s: day in days.get(s, ())  # noqa: E731
    bench = have(BENCHMARK)
    missing = tuple(s for s in universe if not have(s))
    covered = len(universe) - len(missing)
    crit = tuple(sorted(s for s in set(critical) if day not in set(bars.days(s))))
    digest = session_digest(bars, [*universe, BENCHMARK], day)
    reasons: list[str] = []
    state = "READY"
    if now < finalized_at(session):
        state, reasons = "WAIT_DATA", [f"session {day} is not final until {finalized_at(session).isoformat()}"]
    elif not bench:
        state, reasons = "WAIT_DATA", [f"no {BENCHMARK} bar for {day}: the vendor has not published the session, or the data is stale"]
    elif D(covered) / D(len(universe)) < MIN_COVERAGE:
        state, reasons = "WAIT_DATA", [f"only {covered}/{len(universe)} symbols have a bar for {day} (need {int(MIN_COVERAGE * 100)}%)"]
    elif crit and now < session.close + CRITICAL_GRACE:
        state, reasons = "WAIT_CRITICAL", [f"waiting for the bar of held/ordered {', '.join(crit)} (grace until {(session.close + CRITICAL_GRACE).isoformat()})"]
    return SessionAssessment(day, state, covered, len(universe), bench, missing, crit, digest, tuple(reasons))


def dividends_on(market_dir: Path, symbols: Iterable[str], day: date) -> dict[str, str]:
    """Ex-dividend amounts per share on ``day`` for ``symbols``. The ledger is price-return accounting: these are reported, not credited."""
    out = {}
    for s in sorted(set(symbols)):
        for r in cache.read(s, market_dir):
            if r.day == day and r.dividend > 0:
                out[s] = format(r.dividend, "f")
    return out
