"""The strategy interface every shark implements. Hunter is the first.

A strategy is a pure function of point-in-time inputs: it sees bars that had closed by the
decision time and its own sleeve's holdings, and returns proposals. It never sizes in shares
beyond a stop distance, never talks to the ledger, a broker or a model, and cannot reach
another sleeve. Sizing, limits, tradability and fills belong to the shared engine.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Mapping, Protocol, Sequence

from the_reef.market.bars import DailyBar
from the_reef.market.instruments import Intent


@dataclass(frozen=True)
class HoldingView:
    shares: int
    avg_cost: Decimal
    stop_price: Decimal | None


@dataclass(frozen=True)
class StrategyContext:
    session_day: date
    as_of: datetime  # decision time; every bar here closed at or before it
    bars: Mapping[str, Sequence[DailyBar]]  # point-in-time history per symbol, oldest first
    holdings: Mapping[str, HoldingView]  # this sleeve only
    blocked: frozenset[str] = frozenset()  # symbols with an order already pending in this sleeve


@dataclass(frozen=True)
class Proposal:
    symbol: str
    intent: Intent
    score: Decimal  # ranking among entries; higher is better
    ref_price: Decimal  # the close the decision was made on
    stop_price: Decimal | None  # invalidation price for OPEN/ADD
    rationale: str


@dataclass(frozen=True)
class Review:
    """What a strategy wants done with what its sleeve already holds."""

    exits: tuple[Proposal, ...] = ()
    new_stops: Mapping[str, Decimal] = field(default_factory=dict)  # only ever raised by the engine


class Strategy(Protocol):
    strategy_id: str

    @property
    def spec_hash(self) -> str: ...

    def propose(self, ctx: StrategyContext) -> Sequence[Proposal]: ...

    def review(self, ctx: StrategyContext) -> Review: ...


def spec_hash(strategy_id: str, version: str, params: Mapping[str, object]) -> str:
    body = json.dumps({"id": strategy_id, "version": version, "params": {k: str(v) for k, v in sorted(params.items())}},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()[:16]
