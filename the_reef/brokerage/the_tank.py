"""The Tank — paper brokerage backed by MongoDB Atlas.

State lives in Atlas, not in files. No git commits for data.
Requires MONGODB_URI environment variable.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

from pymongo import MongoClient, DESCENDING
from pymongo.database import Database
from pymongo.collection import Collection

STARTING_CASH = 10000.0
DB_NAME = os.environ.get("MONGODB_DB", "the_reef")


# ── connection ────────────────────────────────────────────────────────────────

_client: Optional[MongoClient] = None


def get_db() -> Database:
    global _client
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise EnvironmentError("MONGODB_URI environment variable is not set")
    if _client is None:
        _client = MongoClient(uri)
    return _client.get_database(DB_NAME)


# ── domain models ─────────────────────────────────────────────────────────────

@dataclass
class Position:
    ticker: str
    shares: float
    entry_price: float
    current_price: float
    entry_time: str
    stop_loss: Optional[float]
    target_price: Optional[float]
    surfaced_by: str
    vetted_by: str
    conviction: int

    @property
    def cost_basis(self) -> float:
        return self.entry_price * self.shares

    @property
    def market_value(self) -> float:
        return self.current_price * self.shares

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        return (self.unrealized_pnl / self.cost_basis) * 100 if self.cost_basis else 0.0


@dataclass
class Trade:
    id: int
    ticker: str
    action: str
    shares: float
    price: float
    timestamp: str
    surfaced_by: str
    vetted_by: str
    conviction: int
    stop_loss: Optional[float]
    target_price: Optional[float]
    reason: str
    outcome: str = "open"
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    pnl: Optional[float] = None


# ── TheTank ───────────────────────────────────────────────────────────────────

class TheTank:
    """Paper brokerage — Apex Shark's execution layer backed by MongoDB Atlas."""

    def __init__(self, db: Optional[Database] = None):
        self._db = db or get_db()
        self._ensure_initialized()

    def _ensure_initialized(self):
        portfolio = self._db.portfolio
        if not portfolio.find_one({"_id": "main"}):
            now = _now()
            portfolio.insert_one({
                "_id": "main",
                "cash": STARTING_CASH,
                "starting_cash": STARTING_CASH,
                "next_trade_id": 1,
                "created_at": now,
            })
            self._db.portfolio_snapshots.insert_one({
                "timestamp": now,
                "portfolio_value": STARTING_CASH,
                "cash": STARTING_CASH,
                "equity": 0.0,
                "event": "init",
            })

    # ── collections ──────────────────────────────────────────────────────────

    @property
    def _portfolio(self) -> Collection:
        return self._db.portfolio

    @property
    def _positions(self) -> Collection:
        return self._db.positions

    @property
    def _trades(self) -> Collection:
        return self._db.trades

    # ── read-only state ───────────────────────────────────────────────────────

    @property
    def _state(self) -> dict:
        doc = self._portfolio.find_one({"_id": "main"})
        assert doc is not None
        return doc

    @property
    def cash(self) -> float:
        return self._state["cash"]

    @property
    def starting_cash(self) -> float:
        return self._state["starting_cash"]

    @property
    def positions(self) -> dict[str, Position]:
        return {
            doc["_id"]: Position(
                ticker=doc["_id"],
                shares=doc["shares"],
                entry_price=doc["entry_price"],
                current_price=doc["current_price"],
                entry_time=doc["entry_time"],
                stop_loss=doc.get("stop_loss"),
                target_price=doc.get("target_price"),
                surfaced_by=doc["surfaced_by"],
                vetted_by=doc["vetted_by"],
                conviction=doc["conviction"],
            )
            for doc in self._positions.find()
        }

    @property
    def trade_history(self) -> list[Trade]:
        return [
            Trade(
                id=doc["id"],
                ticker=doc["ticker"],
                action=doc["action"],
                shares=doc["shares"],
                price=doc["price"],
                timestamp=doc["timestamp"],
                surfaced_by=doc["surfaced_by"],
                vetted_by=doc["vetted_by"],
                conviction=doc["conviction"],
                stop_loss=doc.get("stop_loss"),
                target_price=doc.get("target_price"),
                reason=doc.get("reason", ""),
                outcome=doc.get("outcome", "open"),
                exit_price=doc.get("exit_price"),
                exit_time=doc.get("exit_time"),
                pnl=doc.get("pnl"),
            )
            for doc in self._trades.find().sort("id", DESCENDING)
        ]

    def portfolio_value(self) -> float:
        return self.cash + sum(p.market_value for p in self.positions.values())

    def total_pnl(self) -> float:
        return self.portfolio_value() - self.starting_cash

    def total_pnl_pct(self) -> float:
        return (self.total_pnl() / self.starting_cash) * 100

    def max_position_size(self, conviction: int) -> float:
        pct = min(0.10 + (conviction / 10) * 0.25, 0.35)
        return self.portfolio_value() * pct

    # ── trade execution ───────────────────────────────────────────────────────

    def buy(
        self,
        ticker: str,
        shares: float,
        price: float,
        surfaced_by: str,
        vetted_by: str,
        conviction: int,
        stop_loss: Optional[float] = None,
        target_price: Optional[float] = None,
        reason: str = "",
    ) -> tuple[bool, str]:
        cost = round(shares * price, 2)
        if cost > self.cash:
            return False, f"Insufficient cash: need ${cost:.2f}, have ${self.cash:.2f}"
        if cost > self.max_position_size(conviction):
            return False, (
                f"Position too large for conviction {conviction}: "
                f"max ${self.max_position_size(conviction):.2f}"
            )

        now = _now()
        existing = self._positions.find_one({"_id": ticker})

        if existing:
            old_shares, old_price = existing["shares"], existing["entry_price"]
            new_shares = old_shares + shares
            avg_price = ((old_shares * old_price) + (shares * price)) / new_shares
            self._positions.update_one(
                {"_id": ticker},
                {"$set": {
                    "shares": round(new_shares, 6),
                    "entry_price": round(avg_price, 4),
                    "current_price": price,
                    "stop_loss": stop_loss or existing.get("stop_loss"),
                    "target_price": target_price or existing.get("target_price"),
                }},
            )
        else:
            self._positions.insert_one({
                "_id": ticker,
                "shares": shares,
                "entry_price": price,
                "current_price": price,
                "entry_time": now,
                "stop_loss": stop_loss,
                "target_price": target_price,
                "surfaced_by": surfaced_by,
                "vetted_by": vetted_by,
                "conviction": conviction,
            })

        trade_id = self._next_trade_id()
        self._trades.insert_one({
            "id": trade_id,
            "ticker": ticker,
            "action": "BUY",
            "shares": shares,
            "price": price,
            "timestamp": now,
            "surfaced_by": surfaced_by,
            "vetted_by": vetted_by,
            "conviction": conviction,
            "stop_loss": stop_loss,
            "target_price": target_price,
            "reason": reason,
            "outcome": "open",
            "exit_price": None,
            "exit_time": None,
            "pnl": None,
        })
        self._portfolio.update_one({"_id": "main"}, {"$inc": {"cash": -cost}})
        self._snapshot("BUY")

        return True, f"BUY {shares} {ticker} @ ${price:.2f} | cost ${cost:.2f} | stop ${stop_loss}"

    def sell(
        self,
        ticker: str,
        shares: float,
        price: float,
        reason: str = "",
        outcome: str = "closed_win",
    ) -> tuple[bool, str]:
        existing = self._positions.find_one({"_id": ticker})
        if not existing:
            return False, f"No open position in {ticker}"

        pos = Position(
            ticker=ticker,
            shares=existing["shares"],
            entry_price=existing["entry_price"],
            current_price=price,
            entry_time=existing["entry_time"],
            stop_loss=existing.get("stop_loss"),
            target_price=existing.get("target_price"),
            surfaced_by=existing["surfaced_by"],
            vetted_by=existing["vetted_by"],
            conviction=existing["conviction"],
        )

        sell_shares = min(shares, pos.shares)
        proceeds = round(sell_shares * price, 2)
        pnl = round((price - pos.entry_price) * sell_shares, 2)
        actual_outcome = outcome if pnl >= 0 else "closed_loss"
        now = _now()

        remaining = round(pos.shares - sell_shares, 6)
        if remaining < 0.0001:
            self._positions.delete_one({"_id": ticker})
        else:
            self._positions.update_one({"_id": ticker}, {"$set": {"shares": remaining}})

        self._portfolio.update_one({"_id": "main"}, {"$inc": {"cash": proceeds}})

        trade_id = self._next_trade_id()
        self._trades.insert_one({
            "id": trade_id,
            "ticker": ticker,
            "action": "SELL",
            "shares": sell_shares,
            "price": price,
            "timestamp": now,
            "surfaced_by": pos.surfaced_by,
            "vetted_by": pos.vetted_by,
            "conviction": pos.conviction,
            "stop_loss": pos.stop_loss,
            "target_price": pos.target_price,
            "reason": reason,
            "outcome": actual_outcome,
            "exit_price": price,
            "exit_time": now,
            "pnl": pnl,
        })

        # Close out the open BUY record
        self._trades.update_one(
            {"ticker": ticker, "action": "BUY", "outcome": "open"},
            {"$set": {"outcome": actual_outcome, "exit_price": price, "exit_time": now, "pnl": pnl}},
        )

        self._snapshot("SELL")
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        return True, f"SELL {sell_shares} {ticker} @ ${price:.2f} | P&L {pnl_str} | {actual_outcome}"

    def update_prices(self, prices: dict[str, float]):
        for ticker, price in prices.items():
            self._positions.update_one({"_id": ticker}, {"$set": {"current_price": price}})

    def check_stop_losses(self) -> list[tuple[str, float]]:
        triggered = []
        for doc in self._positions.find():
            stop = doc.get("stop_loss")
            if stop and doc["current_price"] <= stop:
                triggered.append((doc["_id"], doc["current_price"]))
        return triggered

    def take_snapshot(self, event: str = "daily_report") -> None:
        self._snapshot(event)

    def log_decision(self, ticker: str, signal_type: str, decision: str, conviction: int, rationale: str):
        """Persist Apex Shark's decision reasoning to the decisions collection."""
        self._db.decisions.insert_one({
            "ticker": ticker,
            "signal_type": signal_type,
            "decision": decision,
            "conviction": conviction,
            "rationale": rationale[:2000],
            "timestamp": _now(),
        })

    def summary(self) -> str:
        positions = self.positions
        lines = [
            f"The Tank | Portfolio: ${self.portfolio_value():.2f} | "
            f"P&L: {'+' if self.total_pnl() >= 0 else ''}${self.total_pnl():.2f} "
            f"({self.total_pnl_pct():+.1f}%) | Cash: ${self.cash:.2f}",
        ]
        for ticker, p in positions.items():
            lines.append(
                f"  {ticker}: {p.shares} shares @ ${p.entry_price:.2f} | "
                f"now ${p.current_price:.2f} | P&L {p.unrealized_pnl_pct:+.1f}% | "
                f"stop ${p.stop_loss} | surfaced by {p.surfaced_by}"
            )
        return "\n".join(lines)

    # ── internal ──────────────────────────────────────────────────────────────

    def _snapshot(self, event: str = "") -> None:
        value = self.portfolio_value()
        self._db.portfolio_snapshots.insert_one({
            "timestamp": _now(),
            "portfolio_value": round(value, 2),
            "cash": round(self.cash, 2),
            "equity": round(value - self.cash, 2),
            "event": event,
        })

    def _next_trade_id(self) -> int:
        result = self._portfolio.find_one_and_update(
            {"_id": "main"},
            {"$inc": {"next_trade_id": 1}},
            return_document=True,
        )
        return result["next_trade_id"] - 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
