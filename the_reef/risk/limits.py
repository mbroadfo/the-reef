"""Risk limits: provisional, configurable, validated (decisions D8a-D8f).

Values are fractions of fund NAV as ``Decimal``. They are inputs to pure functions, never read
from the environment here; the caller loads them from config and passes them in.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Mapping

D = Decimal


@dataclass(frozen=True)
class RiskLimits:
    max_position_pct: Decimal = D("0.10")  # D8: single position, of NAV
    risk_per_trade_pct: Decimal = D("0.005")  # D8f: equity at risk per trade (entry - stop)
    max_sector_pct: Decimal = D("0.25")
    max_unknown_sector_pct: Decimal = D("0.10")  # D8c
    max_invested_pct: Decimal = D("0.60")
    daily_loss_pause_pct: Decimal = D("0.02")  # D8a: vs prior-close NAV
    drawdown_pause_pct: Decimal = D("0.10")  # D8b: vs high-water mark
    min_history_sessions: int = 60  # I-3

    def __post_init__(self) -> None:
        for name in (
            "max_position_pct",
            "risk_per_trade_pct",
            "max_sector_pct",
            "max_unknown_sector_pct",
            "max_invested_pct",
            "daily_loss_pause_pct",
            "drawdown_pause_pct",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
            if not (D("0") < value <= D("1")):
                raise ValueError(f"{name} must be in (0, 1], got {value}")
        if self.max_unknown_sector_pct > self.max_sector_pct:
            raise ValueError("max_unknown_sector_pct must not exceed max_sector_pct")
        if self.risk_per_trade_pct > self.max_position_pct:
            raise ValueError("risk_per_trade_pct must not exceed max_position_pct")
        if self.min_history_sessions < 0:
            raise ValueError("min_history_sessions must be >= 0")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "RiskLimits":
        """Build from config. Unknown keys are an error so a typo cannot silently use a default."""
        known = set(cls.__dataclass_fields__)
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown risk limit keys: {sorted(unknown)}")
        kwargs: dict[str, object] = {}
        for key, value in raw.items():
            kwargs[key] = int(str(value)) if key == "min_history_sessions" else D(str(value))
        return cls(**kwargs)  # type: ignore[arg-type]

    def with_overrides(self, **changes: object) -> "RiskLimits":
        return replace(self, **changes)  # type: ignore[arg-type]
