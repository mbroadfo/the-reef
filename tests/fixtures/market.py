"""Cached test data: a static NYSE calendar and the instrument facts behind defect E-9."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from the_reef.market.calendar import Session, StaticCalendar
from the_reef.market.instruments import (
    CorporateAction,
    CorporateActionKind,
    InstrumentRecord,
    InstrumentStatus,
    StaticCorporateActions,
    StaticInstrumentMaster,
)

NY = ZoneInfo("America/New_York")
FIXTURE = Path(__file__).with_name("nyse_2026_h2.json")


def load_calendar() -> StaticCalendar:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    sessions = []
    for s in raw["sessions"]:
        o = datetime.fromisoformat(s["open_utc"]).astimezone(timezone.utc)
        c = datetime.fromisoformat(s["close_utc"]).astimezone(timezone.utc)
        sessions.append(Session(date.fromisoformat(s["day"]), o, c, early_close=c.astimezone(NY).hour < 16))
    return StaticCalendar(sessions, date.fromisoformat(raw["start"]), date.fromisoformat(raw["end"]))


# Sources for SEM: Select Medical Holdings Corporation, CIK 1320414. Verified on EDGAR 2026-10-30:
# Form 8-K accession 0001104659-26-079643 (Exhibit 99.1 dated 2026-06-30: acquisition effective
# 2026-07-01 12:01 am at $16.50 per share; stock ceases trading and NYSE listing ends 2026-07-01),
# Form 25-NSE 0000876661-26-000585 (filed 2026-07-01).
SEM_EVIDENCE = (
    "SEC 8-K 0001104659-26-079643 Ex.99.1",
    "SEC Form 25-NSE 0000876661-26-000585",
)

UTC = timezone.utc
SEM_ACTIVE = InstrumentRecord(  # what was knowable before the deal closed
    symbol="SEM",
    exchange="NYSE",
    status=InstrumentStatus.ACTIVE,
    first_trade_date=date(2005, 4, 1),
    last_trade_date=None,
    sector="Healthcare",
    source="fixture",
    as_of=datetime(2020, 1, 1, tzinfo=UTC),
)
SEM = InstrumentRecord(
    symbol="SEM",
    exchange="NYSE",
    status=InstrumentStatus.ACQUIRED,
    first_trade_date=date(2005, 4, 1),  # placeholder: only has to be long ago
    last_trade_date=date(2026, 6, 30),
    sector="Healthcare",
    source="fixture",
    as_of=datetime(2026, 7, 1, tzinfo=UTC),
)
# The announcement date is not verified here; tests only need it before 2026-06-22.
SEM_DEAL = CorporateAction(
    symbol="SEM",
    kind=CorporateActionKind.CASH_ACQUISITION,
    announced=date(2025, 12, 1),
    effective=date(2026, 7, 1),
    known_at=datetime(2025, 12, 1, tzinfo=UTC),  # placeholder, same as `announced`
    cash_per_share=Decimal("16.50"),
    evidence=SEM_EVIDENCE,
)


def _active(symbol: str, first: date, sector: str | None = "Technology") -> InstrumentRecord:
    return InstrumentRecord(symbol, "NASDAQ", InstrumentStatus.ACTIVE, first, None, sector, "fixture",
                            datetime.combine(max(first, date(2020, 1, 1)), datetime.min.time(), tzinfo=UTC))


def standard_master() -> StaticInstrumentMaster:
    return StaticInstrumentMaster(
        [
            SEM_ACTIVE,
            SEM,
            _active("AAPL", date(1980, 12, 12)),
            _active("FIZZ", date(1991, 9, 13), "Consumer"),
            _active("SPCX", date(2026, 6, 12)),  # a fresh listing, for minimum-history tests
            InstrumentRecord("HALT", "NYSE", InstrumentStatus.HALTED, date(2010, 1, 4), None, "Industrials", "fixture", datetime(2020, 1, 1, tzinfo=UTC)),
            InstrumentRecord("GONE", "NYSE", InstrumentStatus.DELISTED, date(2010, 1, 4), date(2026, 3, 2), None, "fixture", datetime(2026, 3, 3, tzinfo=UTC)),
            _active("NOSEC", date(2015, 1, 5), None),
        ]
    )


def standard_actions() -> StaticCorporateActions:
    return StaticCorporateActions([SEM_DEAL])
