"""Adapters from ledger state to the Risk Engine's ``PortfolioView``.

The fund view aggregates every sleeve (position and sector caps are fund-wide); the sleeve's own
cash is passed to the engine separately as ``sleeve_cash``. A position without a valid mark is
carried at cost in the view and flips ``book_trusted`` to False, which blocks new entries and
never blocks exits (defect E-6: an unmarkable position must not be silently valued).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from the_reef.ledger.state import EpochState
from the_reef.risk.engine import PortfolioView, PositionView


def fund_view(
    epoch: EpochState,
    marks: Mapping[str, Decimal | None],
    sectors: Mapping[str, str | None],
    *,
    prior_close_nav: Decimal,
    high_water_mark: Decimal,
) -> PortfolioView:
    positions: list[PositionView] = []
    trusted = True
    for sid in sorted(epoch.sleeves):
        for sym, pos in sorted(epoch.sleeves[sid].positions.items()):
            mark = marks.get(sym)
            if mark is None or mark <= 0:
                trusted = False
                mark = pos.avg_cost
            positions.append(PositionView(sym, pos.shares, mark, sectors.get(sym), pos.stop_price))
    invested = sum((p.value for p in positions), Decimal("0"))
    return PortfolioView(
        nav=epoch.cash + invested, cash=epoch.cash, prior_close_nav=prior_close_nav,
        high_water_mark=high_water_mark, positions=tuple(positions), book_trusted=trusted,
    )


def sleeve_cash(epoch: EpochState, sleeve_id: str) -> Decimal:
    return epoch.sleeves[sleeve_id].cash
