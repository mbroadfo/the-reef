from __future__ import annotations

from decimal import Decimal

import pytest

from the_reef.risk.limits import RiskLimits

D = Decimal


def test_defaults_are_the_provisional_values():
    lim = RiskLimits()
    assert (lim.max_position_pct, lim.risk_per_trade_pct, lim.max_sector_pct) == (D("0.10"), D("0.005"), D("0.25"))
    assert (lim.max_invested_pct, lim.daily_loss_pause_pct, lim.drawdown_pause_pct) == (D("0.60"), D("0.02"), D("0.10"))
    assert lim.max_unknown_sector_pct == D("0.10") and lim.min_history_sessions == 60


@pytest.mark.parametrize("field", ["max_position_pct", "risk_per_trade_pct", "max_sector_pct", "max_invested_pct"])
@pytest.mark.parametrize("bad", [D("0"), D("-0.1"), D("1.5")])
def test_out_of_range_values_are_rejected(field, bad):
    with pytest.raises(ValueError):
        RiskLimits(**{field: bad})


def test_floats_are_rejected_to_avoid_silent_rounding():
    with pytest.raises(TypeError):
        RiskLimits(max_position_pct=0.1)  # type: ignore[arg-type]


def test_cross_field_rules():
    with pytest.raises(ValueError):
        RiskLimits(max_unknown_sector_pct=D("0.30"))
    with pytest.raises(ValueError):
        RiskLimits(risk_per_trade_pct=D("0.20"))


def test_from_mapping_rejects_typos_and_converts_strings():
    lim = RiskLimits.from_mapping({"max_position_pct": "0.08", "min_history_sessions": "40"})
    assert lim.max_position_pct == D("0.08") and lim.min_history_sessions == 40
    with pytest.raises(ValueError):
        RiskLimits.from_mapping({"max_postion_pct": "0.08"})


def test_overrides_return_a_new_validated_object():
    base = RiskLimits()
    changed = base.with_overrides(max_invested_pct=D("0.5"))
    assert base.max_invested_pct == D("0.60") and changed.max_invested_pct == D("0.5")
    with pytest.raises(ValueError):
        base.with_overrides(max_invested_pct=D("2"))
