"""Regenerate tests/fixtures/nyse_2026_h2.json from exchange_calendars.

Run only to refresh the cached data: python tests/fixtures/generate_nyse_fixture.py
The calendar agreement test fails if the library and this cache ever disagree.
"""
import json
from pathlib import Path

import exchange_calendars as xc

START, END = "2026-06-01", "2026-12-31"
cal = xc.get_calendar("XNYS")
sessions = []
for ts in cal.sessions_in_range(START, END):
    sessions.append(
        {
            "day": ts.date().isoformat(),
            "open_utc": cal.session_open(ts).tz_convert("UTC").isoformat(),
            "close_utc": cal.session_close(ts).tz_convert("UTC").isoformat(),
        }
    )
out = {"calendar": "XNYS", "start": START, "end": END, "library": f"exchange_calendars {xc.__version__}", "sessions": sessions}
Path(__file__).with_name("nyse_2026_h2.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
print(len(sessions), "sessions")
