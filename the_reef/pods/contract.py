"""The shared proposal contract: what every pod submits to Apex, whatever its strategy.

A packet is plain JSON-able data written into the ledger as PROPOSAL_SUBMITTED, so what Apex was
shown is part of the permanent, hash-chained record. Money is a string, shares are ints.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from the_reef.strategy.base import Proposal

D = Decimal


def proposal_id(pod_id: str, day: date, symbol: str) -> str:
    return f"{pod_id}:{day.isoformat()}:{symbol}"


def build_packet(*, pod_id: str, strategy: Any, prop: Proposal, day: date, created_at: datetime, sleeve_cash: Decimal,
                 sector: str | None) -> dict[str, Any]:
    assert prop.stop_price is not None and prop.stop_price < prop.ref_price
    fraction = getattr(strategy, "request_fraction", D("1"))  # a bare strategy asks for all of its sleeve cash
    ask = (sleeve_cash * fraction).quantize(D("0.01"), rounding=ROUND_FLOOR)
    shares = int((ask / prop.ref_price).to_integral_value(rounding=ROUND_FLOOR))
    risk_per_share = prop.ref_price - prop.stop_price
    return {
        "proposal_id": proposal_id(pod_id, day, prop.symbol),
        "pod_id": pod_id,
        "sleeve_id": pod_id,
        "symbol": prop.symbol,
        "intent": prop.intent.value,
        "sector": sector,
        "thesis": prop.thesis or prop.rationale,
        "findings": [
            {"agent": f.agent, "role": f.role, "verdict": f.verdict, "summary": f.summary,
             "metrics": [{"label": k, "value": v} for k, v in f.metrics]}
            for f in prop.findings
        ],
        "rationale": prop.rationale,
        "created_at": created_at.isoformat(),
        "as_of_session": day.isoformat(),
        "score": format(prop.score, "f"),
        "entry_plan": {"type": "next_valid_open", "reference_price": format(prop.ref_price, "f"),
                       "reference": f"close of {day.isoformat()}"},
        "exit_plan": {"stop_price": format(prop.stop_price, "f"),
                      "rules": list(getattr(strategy, "exit_rules", ())) or ["Resting stop only"]},
        "risk": {"risk_per_share": format(risk_per_share, "f"),
                 "stop_distance_pct": format((risk_per_share / prop.ref_price * 100).quantize(D("0.01")), "f"),
                 "risk_at_request": format((risk_per_share * shares).quantize(D("0.01")), "f")},
        "capital_request": {"dollars": format(ask, "f"), "shares": shares, "fraction_of_sleeve_cash": format(fraction, "f")},
        "strategy": f"{strategy.strategy_id}@{strategy.spec_hash}",
    }
