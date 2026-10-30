from __future__ import annotations

import random
from decimal import Decimal

import pytest

from the_reef.risk.engine import (
    PortfolioView,
    PositionView,
    RejectCode,
    Rule,
    daily_loss_paused,
    drawdown_paused,
    evaluate_entry,
    evaluate_exit,
    sector_exposure,
    size_order,
)
from the_reef.risk.limits import RiskLimits

D = Decimal
LIM = RiskLimits()


def pf(cash="10000", positions=(), nav=None, prior="10000", hwm="10000", trusted=True):
    positions = tuple(positions)
    invested = sum((p.value for p in positions), D("0"))
    return PortfolioView(
        nav=D(nav) if nav is not None else D(cash) + invested,
        cash=D(cash), prior_close_nav=D(prior), high_water_mark=D(hwm), positions=positions, book_trusted=trusted,
    )


def pos(symbol, shares, price, sector: str | None = "Technology"):
    return PositionView(symbol, shares, D(str(price)), sector)


def entry(portfolio, symbol="NEW", sector: str | None = "Healthcare", ref="42", stop="39", sleeve="1666.67", requested=None, limits=LIM):
    return evaluate_entry(
        symbol=symbol, sector=sector, ref_price=D(ref), stop_price=D(stop), sleeve_cash=D(sleeve),
        portfolio=portfolio, limits=limits, requested_shares=requested,
    )


# --- sizing ---------------------------------------------------------------------------------

def test_worked_sizing_example_from_the_design():
    s = size_order(nav=D(10000), ref_price=D(42), stop_price=D(39), sleeve_cash=D("1666.67"), limits=LIM)
    assert s is not None and s.shares == 16 and s.binding is Rule.RISK_PER_TRADE
    assert s.by_cap.quantize(D("0.1")) == D("23.8")


def test_position_cap_binds_with_a_tight_stop():
    s = size_order(nav=D(10000), ref_price=D(42), stop_price=D(41), sleeve_cash=D(5000), limits=LIM)
    assert s is not None and s.shares == 23 and s.binding is Rule.POSITION_CAP


def test_sleeve_cash_binds_when_the_sleeve_is_nearly_empty():
    s = size_order(nav=D(10000), ref_price=D(42), stop_price=D(39), sleeve_cash=D(100), limits=LIM)
    assert s is not None and s.shares == 2 and s.binding is Rule.SLEEVE_CASH


def test_whole_shares_only_and_a_stock_above_the_cap_gets_zero():
    s = size_order(nav=D(10000), ref_price=D(1500), stop_price=D(1400), sleeve_cash=D(5000), limits=LIM)
    assert s is not None and s.shares == 0


@pytest.mark.parametrize("kw", [dict(stop_price=D(42)), dict(stop_price=D(50)), dict(ref_price=D(0)), dict(nav=D(0)), dict(stop_price=D(0)), dict(sleeve_cash=D(-1))])
def test_invalid_sizing_inputs_return_none(kw):
    base = dict(nav=D(10000), ref_price=D(42), stop_price=D(39), sleeve_cash=D(1000), limits=LIM)
    base.update(kw)
    assert size_order(**base) is None


# --- pauses ---------------------------------------------------------------------------------

def test_daily_loss_pause_boundary():
    assert daily_loss_paused(D(9800), D(10000), LIM)
    assert not daily_loss_paused(D(9801), D(10000), LIM)
    assert not daily_loss_paused(D(10500), D(10000), LIM)
    assert not daily_loss_paused(D(100), D(0), LIM)


def test_drawdown_pause_boundary():
    assert drawdown_paused(D(9000), D(10000), LIM)
    assert not drawdown_paused(D("9000.01"), D(10000), LIM)


def test_pauses_block_entries_but_never_exits():
    held = [pos("AAPL", 10, 100)]
    daily = pf(cash="8000", positions=held, nav="9700", prior="10000")
    dd = pf(cash="8000", positions=held, nav="8900", hwm="10000", prior="8900")
    untrusted = pf(cash="9000", positions=held, trusted=False)
    assert entry(daily).reasons == (RejectCode.DAILY_LOSS_PAUSE,)
    assert entry(dd).reasons == (RejectCode.DRAWDOWN_PAUSE,)
    assert entry(untrusted).reasons == (RejectCode.BOOK_UNTRUSTED,)
    for p in (daily, dd, untrusted):
        assert evaluate_exit(symbol="AAPL", requested_shares=10, portfolio=p).approved


def test_multiple_pauses_are_all_reported():
    p = pf(cash="8000", positions=[pos("AAPL", 10, 100)], nav="8000", prior="10000", hwm="10000", trusted=False)
    assert set(entry(p).reasons) == {RejectCode.BOOK_UNTRUSTED, RejectCode.DAILY_LOSS_PAUSE, RejectCode.DRAWDOWN_PAUSE}


# --- limits and clamps ----------------------------------------------------------------------

def test_clean_entry_is_approved_unclamped():
    d = entry(pf())
    assert d.approved and d.shares == 16 and d.clamps == ()


def test_max_invested_clamps_and_does_not_redistribute():
    p = pf(cash="4100", positions=[pos("AAPL", 59, 100)])  # 59% invested
    d = entry(p, symbol="FIZZ", sector="Consumer")
    assert d.approved and d.shares == 2
    assert [(c.rule, c.requested_shares, c.allowed_shares) for c in d.clamps] == [(Rule.MAX_INVESTED, 16, 2)]


def test_entry_rejected_when_already_at_max_invested():
    p = pf(cash="4000", positions=[pos("AAPL", 60, 100)])
    d = entry(p, symbol="FIZZ", sector="Consumer")
    assert not d.approved and d.reasons == (RejectCode.MAX_INVESTED,)


def test_sector_cap_clamps():
    p = pf(cash="7600", positions=[pos("AAPL", 24, 100)])  # Technology 24%
    d = entry(p, symbol="MSFT", sector="Technology")
    assert d.approved and d.shares == 2 and d.clamps[-1].rule is Rule.SECTOR_CAP


def test_sector_cap_rejects_when_full():
    p = pf(cash="7500", positions=[pos("AAPL", 25, 100)])
    d = entry(p, symbol="MSFT", sector="Technology")
    assert not d.approved and d.reasons == (RejectCode.SECTOR_CAP,)


def test_unknown_sector_uses_the_tighter_cap():
    p = pf(cash="9100", positions=[pos("MYST", 9, 100, sector=None)])  # 9% unknown
    d = entry(p, symbol="NOSEC", sector=None)
    assert d.approved and d.shares == 2 and d.clamps[-1].rule is Rule.SECTOR_CAP
    assert sector_exposure(p)["UNKNOWN"] == D("0.09")


def test_add_counts_the_existing_holding_against_the_position_cap():
    p = pf(cash="9500", positions=[pos("AAPL", 5, 100)])
    d = entry(p, symbol="AAPL", sector="Technology", ref="100", stop="95", sleeve="9000")
    assert d.approved and d.shares == 5 and d.clamps[0].rule is Rule.POSITION_CAP


def test_drifted_position_over_the_cap_blocks_adds_but_is_not_sold():
    p = pf(cash="8800", positions=[pos("AAPL", 12, 100)])  # 12% of NAV
    d = entry(p, symbol="AAPL", sector="Technology", ref="100", stop="95")
    assert not d.approved and d.reasons == (RejectCode.POSITION_AT_CAP,) and "POSITION_OVER_CAP_NO_ADDS" in d.flags


def test_fund_cash_limits_the_order():
    p = pf(cash="100", nav="10000")  # sleeve accounting claims more cash than the fund holds
    d = entry(p, sleeve="5000")
    assert d.approved and d.shares == 2 and d.clamps[0].rule is Rule.FUND_CASH


def test_allocator_ceiling_can_only_lower():
    assert entry(pf(), requested=5).shares == 5
    assert entry(pf(), requested=500).shares == 16  # a larger request is never honoured
    assert entry(pf(), requested=0).approved is False


def test_invalid_entries():
    assert entry(pf(), stop="42").reasons == (RejectCode.INVALID_STOP,)
    assert entry(pf(), stop="45").reasons == (RejectCode.INVALID_STOP,)
    assert entry(pf(), ref="0").reasons == (RejectCode.INVALID_REQUEST,)
    assert entry(pf(), requested=-1).reasons == (RejectCode.INVALID_REQUEST,)


# --- exits ----------------------------------------------------------------------------------

def test_exit_is_capped_at_shares_held_and_reports_the_clamp():
    p = pf(cash="9000", positions=[pos("AAPL", 10, 100)])
    d = evaluate_exit(symbol="AAPL", requested_shares=50, portfolio=p)
    assert d.approved and d.shares == 10 and d.clamps


def test_exit_of_an_unheld_name_is_rejected():
    assert evaluate_exit(symbol="AAPL", requested_shares=1, portfolio=pf()).reasons == (RejectCode.NOT_HELD,)
    assert evaluate_exit(symbol="AAPL", requested_shares=0, portfolio=pf()).reasons == (RejectCode.INVALID_REQUEST,)


# --- invariants -----------------------------------------------------------------------------

def test_decisions_are_deterministic():
    p = pf(cash="4100", positions=[pos("AAPL", 59, 100)])
    assert entry(p, symbol="FIZZ", sector="Consumer") == entry(p, symbol="FIZZ", sector="Consumer")


def test_random_portfolios_never_breach_a_limit():
    rnd = random.Random(20261030)
    sectors = ["Technology", "Healthcare", "Industrials", None]
    approved = 0
    for _ in range(1500):
        nav_target = D(rnd.randint(5000, 50000))
        positions = [
            pos(f"P{i}", rnd.randint(1, 60), round(rnd.uniform(5, 400), 2), rnd.choice(sectors))
            for i in range(rnd.randint(0, 5))
        ]
        invested = sum((p.value for p in positions), D("0"))
        cash = max(nav_target - invested, D("0"))
        p = pf(cash=str(cash), positions=positions, prior=str(cash + invested), hwm=str(cash + invested))
        ref = D(str(round(rnd.uniform(5, 500), 2)))
        stop = (ref * D(str(round(rnd.uniform(0.80, 0.99), 3)))).quantize(D("0.01"))
        if stop <= 0 or stop >= ref:
            continue
        sector = rnd.choice(sectors)
        sym = rnd.choice(["NEW", "P0", "P1"])
        sleeve = D(rnd.randint(0, int(p.nav)))
        d = entry(p, symbol=sym, sector=sector, ref=str(ref), stop=str(stop), sleeve=str(sleeve))
        assert isinstance(d.shares, int) and d.shares >= 0
        if not d.approved:
            assert d.shares == 0 and d.reasons
            continue
        approved += 1
        cost = d.shares * ref
        key = sector
        cap = LIM.max_unknown_sector_pct if key is None else LIM.max_sector_pct
        assert cost <= p.cash
        assert cost <= sleeve
        assert p.invested + cost <= LIM.max_invested_pct * p.nav
        assert p.value_of(sym) + cost <= LIM.max_position_pct * p.nav
        assert p.sector_value(key) + cost <= cap * p.nav
        assert d.shares * (ref - stop) <= LIM.risk_per_trade_pct * p.nav
    assert approved > 100  # the sweep exercised real approvals, not only rejections
