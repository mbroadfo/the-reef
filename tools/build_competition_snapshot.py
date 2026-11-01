"""Run the deterministic two-pod fixture competition on the shared engine and write the aquarium snapshot.

Run:  uv run python tools/build_competition_snapshot.py [--out PATH]
Synthetic prices only. No network, no Atlas, no LLM. Same output on every run.
"""
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from tests.fixtures.competition_scenario import FIRST, SESSIONS, make_comp_deps, make_comp_world
from the_reef.aquarium.snapshot import build_snapshot
from the_reef.engine.advance import advance, bootstrap
from the_reef.ledger.ledger import Ledger

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "dashboard" / "frontend" / "public" / "reef2" / "snapshot.json"
MODE = {
    "kind": "FIXTURE_DEMONSTRATION",
    "label": "Fixture demonstration",
    "disclosure": "Synthetic prices from a seeded generator, run through the real Reef 2.0 engine and ledger. Nothing here is live, "
                  "real money, or a real market, and it shows no evidence of investment skill.",
}


def build() -> dict:
    world = make_comp_world()
    deps = make_comp_deps(world)
    led = Ledger()
    bootstrap(led, deps, world.calendar.session(world.days[FIRST]).open - timedelta(hours=1))
    for i in range(FIRST, FIRST + SESSIONS):
        advance(led, deps, world.days[i])
    return build_snapshot(led, deps, first_session=world.days[FIRST], last_session=world.days[FIRST + SESSIONS - 1], mode=MODE)


def render(snapshot: dict) -> str:
    return json.dumps(snapshot, indent=1, sort_keys=True) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    snap = build()
    out.write_text(render(snap), encoding="utf-8")
    print(f"wrote {out}  ({snap['generated_from']['events']} events, head {snap['generated_from']['head_hash'][:12]})")
    for p in snap["pods"]:
        if p["status"] == "ACTIVE":
            print(f"  #{p['rank']} {p['name']:11} NAV {p['nav']:>9}  return {p['return'] * 100:+.2f}%  trades {p['trades']}  proposals {p['proposals']}")
    print("  checks:", ", ".join(f"{c['name']}={'ok' if c['ok'] else 'FAIL'}" for c in snap["checks"]))


if __name__ == "__main__":
    main()
