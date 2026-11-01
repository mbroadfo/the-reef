"""One command: rebuild the competition snapshot from the engine, then serve the aquarium locally.

Run:  uv run python tools/aquarium_demo.py      (then open the printed URL; Ctrl+C to stop)
Needs Node for the frontend (`npm ci` once in dashboard/frontend). No network services, accounts or costs.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from tools.build_competition_snapshot import DEFAULT_OUT, main as build_main

FRONTEND = Path(__file__).resolve().parents[1] / "dashboard" / "frontend"


def main() -> None:
    sys.argv = [sys.argv[0], "--out", str(DEFAULT_OUT)]
    build_main()
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm not found; install Node, then run `npm ci && npm run dev` in dashboard/frontend")
    print("\nAquarium: http://localhost:5173/   (Research Lab: /lab)\n")
    subprocess.run([npm, "run", "dev"], cwd=FRONTEND, check=False)


if __name__ == "__main__":
    main()
