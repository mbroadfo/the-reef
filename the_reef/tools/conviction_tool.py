"""Conviction bidding system — each shark stakes daily points on their position.

During a dive, each analyst calls ConvictionBidTool to bid 1-10 pts (positive=long,
negative=oppose). The shark with the highest absolute bid sponsors the trade and owns
its P&L attribution. Points reset at market open via reset_conviction_points.py.
"""
from __future__ import annotations

from datetime import datetime, timezone, date
from pydantic import BaseModel, Field
from crewai.tools import BaseTool


SHARKS = [
    "hunter_shark", "research_shark", "macro_shark", "sentiment_shark",
    "contrarian_shark", "risk_shark", "wildcard_shark",
]
POINTS_PER_DAY = 10


def _today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _get_db():
    from ..brokerage.the_tank import get_db
    return get_db()


def _get_or_create_points(db, shark_id: str, today: str) -> dict:
    doc = db.shark_points.find_one({"date": today, "shark_id": shark_id})
    if not doc:
        doc = {
            "date": today,
            "shark_id": shark_id,
            "points_total": POINTS_PER_DAY,
            "points_spent": 0,
            "points_remaining": POINTS_PER_DAY,
            "bids": [],
        }
        db.shark_points.insert_one(doc)
    return doc


class ConvictionBidInput(BaseModel):
    ticker: str = Field(..., description="Ticker being evaluated")
    bid: int = Field(..., ge=-10, le=10, description="Points bid: positive=long conviction, negative=you oppose this trade")
    rationale: str = Field(..., description="One sentence: why you are bidding this amount")


class ConvictionBidTool(BaseTool):
    name: str = "Submit Conviction Bid"
    description: str = (
        "Submit your conviction bid for this ticker. "
        "Positive bid (1-10): you believe in this trade. "
        "Negative bid (-1 to -10): you oppose this trade. "
        "The highest absolute bidder becomes the trade sponsor and owns P&L attribution. "
        "Bid honestly — you have 10 points per day total."
    )
    args_schema: type[BaseModel] = ConvictionBidInput
    shark_id: str = ""

    def _run(self, ticker: str, bid: int, rationale: str) -> str:
        if not self.shark_id:
            return "Error: ConvictionBidTool must be initialized with shark_id set"

        db = _get_db()
        today = _today()
        doc = _get_or_create_points(db, self.shark_id, today)

        abs_bid = abs(bid)
        remaining = doc["points_remaining"]

        # Clamp to remaining — server-side enforcement
        if abs_bid > remaining:
            abs_bid = remaining
            bid = abs_bid if bid > 0 else -abs_bid

        if abs_bid == 0:
            return f"{self.shark_id}: Out of conviction points today. Bid recorded as 0."

        direction = "long" if bid > 0 else "short"
        db.shark_points.update_one(
            {"date": today, "shark_id": self.shark_id},
            {
                "$inc": {"points_spent": abs_bid, "points_remaining": -abs_bid},
                "$push": {"bids": {
                    "ticker": ticker.upper(),
                    "bid": bid,
                    "direction": direction,
                    "rationale": rationale[:200],
                    "timestamp": _now(),
                }},
            },
        )

        new_remaining = remaining - abs_bid
        return (
            f"{self.shark_id} bid {bid:+d} pts on {ticker.upper()} ({direction}). "
            f"Rationale: {rationale[:100]} | Points remaining today: {new_remaining}/10"
        )


class GetConvictionBidsInput(BaseModel):
    ticker: str = Field(..., description="Ticker to retrieve all bids for")


class GetConvictionBidsTool(BaseTool):
    name: str = "Get Conviction Bids"
    description: str = (
        "Retrieve all conviction bids submitted today for this ticker. "
        "Returns bids sorted by absolute magnitude. "
        "Identify the sponsor (highest |bid|) and pass their shark_id as "
        "sponsored_by plus the full bids dict as conviction_bids to Execute Paper Buy."
    )
    args_schema: type[BaseModel] = GetConvictionBidsInput

    def _run(self, ticker: str) -> str:
        db = _get_db()
        today = _today()
        ticker = ticker.upper()

        docs = list(db.shark_points.find({"date": today}))
        bids = []
        for doc in docs:
            for b in doc.get("bids", []):
                if b["ticker"] == ticker:
                    bids.append({
                        "shark_id": doc["shark_id"],
                        "bid": b["bid"],
                        "direction": b["direction"],
                    })

        if not bids:
            return (
                f"No conviction bids found for {ticker} today. "
                "Use sponsored_by='apex_shark' and conviction_bids={} as fallback."
            )

        bids.sort(key=lambda x: abs(x["bid"]), reverse=True)
        sponsor = bids[0]
        bid_dict = {b["shark_id"]: b["bid"] for b in bids}

        lines = [f"Conviction bids for {ticker} ({today}):"]
        for b in bids:
            marker = " <-- SPONSOR" if b["shark_id"] == sponsor["shark_id"] else ""
            lines.append(f"  {b['shark_id']}: {b['bid']:+d} ({b['direction']}){marker}")
        lines.append(f"\nSponsor: {sponsor['shark_id']} ({sponsor['bid']:+d} pts)")
        lines.append(f"Pass to Execute Paper Buy: sponsored_by='{sponsor['shark_id']}', conviction_bids={bid_dict}")
        return "\n".join(lines)
